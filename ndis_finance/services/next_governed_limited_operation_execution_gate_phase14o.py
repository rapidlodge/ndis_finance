import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXECUTION_GATE_ACK = "I_CONFIRM_PHASE14O_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"
EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"

PREVIEW_READY_FIELD = "ready_for_next_governed_limited_op_execution_gate"
EXECUTION_GATE_READY_FIELD = "ready_for_next_governed_limited_op_smoke"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00016"
PREVIOUS_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
HISTORICAL_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
NEXT_SMOKE_PAYMENT_ENTRY = "ACC-PAY-2026-00017"
EXECUTION_GATE_PAYMENT_ENTRY = GATED_PAYMENT_ENTRY
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 15
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 102
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_RESTORED_INVOICE_AMOUNT = 3.00
EXPECTED_GL_ROWS = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00
EXPECTED_ACTUAL_PE_CREATED = 0
EXPECTED_ACTUAL_PE_CANCELLED = 0
EXPECTED_ACTUAL_GL_CREATED = 0

EXECUTION_GATE_SOURCE_DOCTYPE = "Sales Invoice"
EXECUTION_GATE_REFERENCE_DOCTYPE = "Sales Invoice"
EXECUTION_GATE_PARTY_TYPE = "Customer"


def make_execution_gate_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-EXECUTION-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def existing_link(doctype, name):
    return name if name and frappe.db.exists(doctype, name) else None


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


def direct_cancelled_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry, "is_cancelled": 1})


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


def latest_phase14n_preview():
    filters = {
        "status": "Preview Approved",
        "preview_status": "Next Governed Limited Operation Preview Approved",
        "preview_approved": 1,
        "phase14m_candidate_validation_verified": 1,
        "candidate_validation_approved_verified": 1,
        "candidate_validation_payment_entry_verified": 1,
        "candidate_validation_payment_entry_cancelled_verified": 1,
        "candidate_validation_gl_rows_verified": 1,
        "candidate_validation_reversal_gl_rows_verified": 1,
        "candidate_validation_gl_net_zero_verified": 1,
        "candidate_validation_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "preview_payment_entry": GATED_PAYMENT_ENTRY,
        "preview_payment_entry_docstatus": 2,
        "preview_payment_entry_status": "Cancelled",
        "gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "previous_gated_payment_entry": HISTORICAL_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": 2,
        "previous_gated_payment_entry_status": "Cancelled",
        "preview_source_doctype": EXECUTION_GATE_SOURCE_DOCTYPE,
        "preview_reference_doctype": EXECUTION_GATE_REFERENCE_DOCTYPE,
        "preview_party_type": EXECUTION_GATE_PARTY_TYPE,
        "preview_invoice_count": EXPECTED_INVOICE_COUNT,
        "preview_total_amount": EXPECTED_TOTAL_AMOUNT,
        "preview_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "preview_gl_rows": EXPECTED_GL_ROWS,
        "preview_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "preview_gl_net": EXPECTED_GL_NET,
        "payment_entry_count_after": EXPECTED_PAYMENT_ENTRY_COUNT,
        "payment_entry_gl_count_after": EXPECTED_PAYMENT_ENTRY_GL_COUNT,
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
    if has_column(PREVIEW_DOCTYPE, PREVIEW_READY_FIELD):
        filters[PREVIEW_READY_FIELD] = 1

    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "preview_id",
            "preview_source_doctype",
            "preview_reference_doctype",
            "preview_party_type",
            "preview_customer",
            "preview_company",
            "preview_currency",
            "preview_invoice_names",
            "preview_invoice_count",
            "preview_total_amount",
            "preview_restored_invoice_amount",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "previous_gated_payment_entry",
            "previous_gated_payment_entry_docstatus",
            "previous_gated_payment_entry_status",
            "preview_payment_entry",
            "preview_payment_entry_docstatus",
            "preview_payment_entry_status",
            "preview_gl_rows",
            "preview_reversal_gl_rows",
            "preview_gl_net",
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
            "execution_gate",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_execution_gate(preview):
    rows = frappe.get_all(
        EXECUTION_GATE_DOCTYPE,
        filters={
            "preview": preview,
            "status": "Execution Gate Approved",
            "execution_gate_approved": 1,
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
        },
        fields=["name", "execution_gate_id", "gated_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def preview_rows(preview):
    rows = frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        filters={"preview": preview, "category": "Preview Reference", "status": "Pass", "reference_doctype": "Sales Invoice"},
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "preview_amount",
            "outstanding_amount",
            "preview_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )
    result = []
    for idx, row in enumerate(rows, start=1):
        si = (
            frappe.db.get_value(
                "Sales Invoice",
                row.reference_name,
                ["docstatus", "customer", "company", "currency", "outstanding_amount"],
                as_dict=True,
            )
            if frappe.db.exists("Sales Invoice", row.reference_name)
            else None
        )
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "execution_gate_amount": flt(row.preview_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
                    "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
                    "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def execution_gate_total(rows):
    return flt(sum(flt(row.execution_gate_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(preview, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not preview:
        issues.append("No approved Phase 14N preview found for execution gate.")
        return issues

    existing = existing_approved_execution_gate(preview.name)
    if existing:
        issues.append(f"Approved Phase 14O execution gate already exists for this preview: {existing.execution_gate_id} / {existing.gated_payment_entry}")

    state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    historical_state = payment_entry_state(HISTORICAL_GATED_PAYMENT_ENTRY)
    if frappe.db.exists("Payment Entry", NEXT_SMOKE_PAYMENT_ENTRY):
        issues.append(f"Next smoke Payment Entry {NEXT_SMOKE_PAYMENT_ENTRY} already exists before Phase 14O execution gate.")
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry {GATED_PAYMENT_ENTRY} does not exist.")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Gated Payment Entry {GATED_PAYMENT_ENTRY} must be Cancelled before execution gate.")
    if not frappe.db.exists("Payment Entry", PREVIOUS_GATED_PAYMENT_ENTRY):
        issues.append(f"Previous gated Payment Entry {PREVIOUS_GATED_PAYMENT_ENTRY} does not exist.")
    if previous_state.docstatus != 2 or previous_state.status != "Cancelled":
        issues.append(f"Previous gated Payment Entry {PREVIOUS_GATED_PAYMENT_ENTRY} must remain Cancelled before execution gate.")
    if not frappe.db.exists("Payment Entry", HISTORICAL_GATED_PAYMENT_ENTRY):
        issues.append(f"Historical gated Payment Entry {HISTORICAL_GATED_PAYMENT_ENTRY} does not exist.")
    if historical_state.docstatus != 2 or historical_state.status != "Cancelled":
        issues.append(f"Historical gated Payment Entry {HISTORICAL_GATED_PAYMENT_ENTRY} must remain Cancelled before execution gate.")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Execution Gate invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Execution Gate invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if execution_gate_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Execution Gate total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {execution_gate_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_RESTORED_INVOICE_AMOUNT:
        issues.append(f"Restored invoice amount before execution gate must be exactly {EXPECTED_RESTORED_INVOICE_AMOUNT}.")
    if payment_entry_gl_rows(GATED_PAYMENT_ENTRY) != EXPECTED_GL_ROWS:
        issues.append(f"Execution Gate Payment Entry must have {EXPECTED_GL_ROWS} GL rows.")
    if payment_entry_gl_net(GATED_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Execution Gate Payment Entry GL net must be 0.00.")
    if int(preview.preview_reversal_gl_rows or 0) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append("Governed preview reversal rows must remain the four-row delta.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count before Phase 14O must be exactly 15.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count before Phase 14O must be exactly 102.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before execution gate.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before execution gate.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before execution gate.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before execution gate.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for execution gate.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for execution gate.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for execution gate.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append(
            {
                "status": "Pass",
                "severity": "Critical",
                "category": "Execution Gate Source",
                "check_key": "execution_gate_source_valid",
                "check_label": "Execution gate source valid",
                "detail": f"Phase 14N preview evidence for {GATED_PAYMENT_ENTRY} is stable and ready for execution-gate approval.",
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
                "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
                "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Execution Gate Source",
                    "check_key": "execution_gate_source_valid",
                    "check_label": "Execution gate source valid",
                    "detail": issue,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
                    "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
                    "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )

    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Execution Gate Reference",
                "check_key": "execution_gate_sales_invoice_reference",
                "check_label": f"Execution Gate Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} execution gate amount={row.execution_gate_amount}, outstanding={row.outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "execution_gate_amount": row.execution_gate_amount,
                "outstanding_amount": row.outstanding_amount,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
                "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
                "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
            }
        )

    items.append(
        {
            "status": "Pass" if ack_ok else "Warning",
            "severity": "Low" if ack_ok else "Medium",
            "category": "Acknowledgement",
            "check_key": "ack_ok",
            "check_label": "Acknowledgement supplied",
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {EXECUTION_GATE_ACK}",
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
            "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
            "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
        }
    )
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
        row = frappe.new_doc(EXECUTION_GATE_ITEM_DOCTYPE)
        row.execution_gate = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_execution_gate_phase14o(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_execution_gate_phase14o")

    preview = latest_phase14n_preview()
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
    source_issues = validate_source(preview, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    historical_state = payment_entry_state(HISTORICAL_GATED_PAYMENT_ENTRY)
    next_smoke_exists = int(frappe.db.exists("Payment Entry", NEXT_SMOKE_PAYMENT_ENTRY) is not None)
    execution_gate_gl_rows = payment_entry_gl_rows(GATED_PAYMENT_ENTRY)
    execution_gate_gl_net = payment_entry_gl_net(GATED_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(GATED_PAYMENT_ENTRY)

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
    if actual_pe_created != 0:
        post_issues.append(f"Execution gate must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Execution gate must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Execution gate must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after execution gate.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after execution gate.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during execution gate. This is not allowed.")
    if frappe.db.exists("Payment Entry", NEXT_SMOKE_PAYMENT_ENTRY):
        post_issues.append(f"{NEXT_SMOKE_PAYMENT_ENTRY} must not exist during Phase 14O execution gate.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and preview
        and not post_issues
        and state.docstatus == 2
        and state.status == "Cancelled"
        and previous_state.docstatus == 2
        and previous_state.status == "Cancelled"
        and historical_state.docstatus == 2
        and historical_state.status == "Cancelled"
        and not next_smoke_exists
        and execution_gate_gl_rows == EXPECTED_GL_ROWS
        and execution_gate_gl_net == EXPECTED_GL_NET
        and restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and actual_pe_created == EXPECTED_ACTUAL_PE_CREATED
        and actual_pe_cancelled == EXPECTED_ACTUAL_PE_CANCELLED
        and actual_gl_created == EXPECTED_ACTUAL_GL_CREATED
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok)
    item_summary = summarise_items(items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_status": "Next Governed Limited Operation Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_approved": completed,
        "phase14n_preview_verified": 1 if preview else 0,
        "preview_approved_verified": 1 if preview else 0,
        "preview_payment_entry_verified": int(preview and preview.preview_payment_entry == GATED_PAYMENT_ENTRY),
        "preview_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "preview_gl_rows_verified": int(execution_gate_gl_rows == EXPECTED_GL_ROWS),
        "preview_reversal_gl_rows_verified": int(preview and int(preview.preview_reversal_gl_rows or 0) == EXPECTED_REVERSAL_GL_ROWS),
        "preview_gl_net_zero_verified": int(execution_gate_gl_net == EXPECTED_GL_NET),
        "preview_restored_invoice_amount_verified": int(restored_amount == EXPECTED_RESTORED_INVOICE_AMOUNT),
        "next_smoke_payment_entry_absent_verified": int(next_smoke_exists == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": state.docstatus,
        "gated_payment_entry_status": state.status,
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": previous_state.docstatus,
        "previous_gated_payment_entry_status": previous_state.status,
        "historical_gated_payment_entry": HISTORICAL_GATED_PAYMENT_ENTRY,
        "historical_gated_payment_entry_docstatus": historical_state.docstatus,
        "historical_gated_payment_entry_status": historical_state.status,
        "next_smoke_payment_entry": NEXT_SMOKE_PAYMENT_ENTRY,
        "next_smoke_payment_entry_exists": next_smoke_exists,
        "execution_gate_payment_entry": GATED_PAYMENT_ENTRY,
        "execution_gate_payment_entry_docstatus": state.docstatus,
        "execution_gate_payment_entry_status": state.status,
        "execution_gate_source_doctype": EXECUTION_GATE_SOURCE_DOCTYPE,
        "execution_gate_reference_doctype": EXECUTION_GATE_REFERENCE_DOCTYPE,
        "execution_gate_party_type": EXECUTION_GATE_PARTY_TYPE,
        "execution_gate_customer": unique_value(rows, "customer"),
        "execution_gate_company": unique_value(rows, "company"),
        "execution_gate_currency": unique_value(rows, "currency"),
        "execution_gate_invoice_names": ", ".join(reference_names(rows)),
        "execution_gate_invoice_count": len(rows),
        "execution_gate_total_amount": execution_gate_total(rows),
        "execution_gate_restored_invoice_amount": restored_amount,
        "execution_gate_gl_rows": execution_gate_gl_rows,
        "execution_gate_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "execution_gate_gl_net": execution_gate_gl_net,
        "execution_gate_direct_cancelled_gl_rows": direct_cancelled_rows,
        "direct_erpnext_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": preview.target_policy if preview else None,
        "target_policy_name": preview.target_policy_name if preview else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        EXECUTION_GATE_READY_FIELD: completed,
        "preview": preview.name if preview else None,
        "candidate_validation": existing_link("NDIS Next Governed Limited Op Candidate Validation", preview.candidate_validation) if preview else None,
        "candidate_selection": existing_link("NDIS Next Governed Limited Op Candidate Selection", preview.candidate_selection) if preview else None,
        "design": existing_link("NDIS Next Governed Limited Op Design", preview.design) if preview else None,
        "planning": existing_link("NDIS Next Governed Limited Op Planning", preview.planning) if preview else None,
        "monitor": existing_link("NDIS Next Governed Limited Op Runtime Monitor", preview.monitor) if preview else None,
        "baseline": existing_link("NDIS Next Governed Limited Op Steady Baseline", preview.baseline) if preview else None,
        "closeout": existing_link("NDIS Next Governed Limited Op Closeout", preview.closeout) if preview else None,
        "freeze": existing_link("NDIS Next Governed Limited Op Rollback Freeze", preview.freeze) if preview else None,
        "rollback": existing_link("NDIS Next Governed Limited Op Smoke Rollback", preview.rollback) if preview else None,
        "smoke": existing_link("NDIS Next Governed Limited Op Smoke", preview.smoke) if preview else None,
        "previous_execution_gate": existing_link(EXECUTION_GATE_DOCTYPE, preview.execution_gate) if preview else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 14O approves next governed limited-operation execution gate. No accounting movement occurs.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(EXECUTION_GATE_DOCTYPE)
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
    doc.execution_gate_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()

    return {**result, "created": True, "execution_gate": doc.name, "execution_gate_id": doc.execution_gate_id, "gated_payment_entry": GATED_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_execution_gate_phase14o_audit(execution_gate, reason=None):
    assert_action("cancel_next_governed_limited_operation_execution_gate_phase14o_audit")
    if not frappe.db.exists(EXECUTION_GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Next governed limited-operation execution gate audit not found: {0}").format(execution_gate))
    doc = frappe.get_doc(EXECUTION_GATE_DOCTYPE, execution_gate)
    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 14O execution gate record."))
    frappe.db.set_value(
        EXECUTION_GATE_DOCTYPE,
        execution_gate,
        {"status": "Cancelled", "execution_gate_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 14O no-ack execution gate audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{EXECUTION_GATE_ITEM_DOCTYPE}` SET status='Cancelled' WHERE execution_gate=%(execution_gate)s", {"execution_gate": execution_gate})
    frappe.db.commit()
    return {"execution_gate": execution_gate, "status": "Cancelled", "note": "No-ack execution gate audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_execution_gate_phase14o_summary(limit=20):
    return {
        "execution_gate_records": frappe.get_all(
            EXECUTION_GATE_DOCTYPE,
            filters={"gated_payment_entry": GATED_PAYMENT_ENTRY},
            fields=[
                "name",
                "execution_gate_id",
                "status",
                "execution_gate_status",
                "execution_gate_approved",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "previous_gated_payment_entry",
                "previous_gated_payment_entry_docstatus",
                "previous_gated_payment_entry_status",
                "historical_gated_payment_entry",
                "historical_gated_payment_entry_docstatus",
                "historical_gated_payment_entry_status",
                "next_smoke_payment_entry",
                "next_smoke_payment_entry_exists",
                "execution_gate_invoice_names",
                "execution_gate_invoice_count",
                "execution_gate_total_amount",
                "execution_gate_restored_invoice_amount",
                "execution_gate_gl_rows",
                "execution_gate_reversal_gl_rows",
                "execution_gate_gl_net",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                EXECUTION_GATE_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            EXECUTION_GATE_ITEM_DOCTYPE,
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
                "execution_gate_amount",
                "outstanding_amount",
                "gated_payment_entry",
                "previous_gated_payment_entry",
                "next_smoke_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14O next governed limited-operation execution gate summary.",
    }


def execute_execution_gate_phase14o_report(filters=None):
    columns = [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXECUTION_GATE_DOCTYPE, "width": 230},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 570},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 210},
        {"fieldname": "execution_gate_status", "label": _("Execution Gate Status"), "fieldtype": "Data", "width": 470},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "gated_payment_entry", "label": _("Gated Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "gated_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "gated_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "previous_gated_payment_entry", "label": _("Previous Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "historical_gated_payment_entry", "label": _("Historical Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "next_smoke_payment_entry_exists", "label": _("Next Smoke Exists"), "fieldtype": "Check", "width": 120},
        {"fieldname": "execution_gate_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "execution_gate_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "execution_gate_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "execution_gate_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "execution_gate_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "execution_gate_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": EXECUTION_GATE_READY_FIELD, "label": _("Smoke Ready"), "fieldtype": "Check", "width": 120},
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
            name AS execution_gate,
            execution_gate_id,
            status,
            execution_gate_status,
            execution_gate_approved,
            gated_payment_entry,
            gated_payment_entry_docstatus,
            gated_payment_entry_status,
            previous_gated_payment_entry,
            historical_gated_payment_entry,
            next_smoke_payment_entry_exists,
            execution_gate_invoice_names,
            execution_gate_total_amount,
            execution_gate_restored_invoice_amount,
            execution_gate_gl_rows,
            execution_gate_reversal_gl_rows,
            execution_gate_gl_net,
            `{EXECUTION_GATE_READY_FIELD}` AS `{EXECUTION_GATE_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{EXECUTION_GATE_DOCTYPE}`
        WHERE gated_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": GATED_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.execution_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Execution Gate Approved", "values": [int(row.execution_gate_approved or 0) for row in data[:20]]},
                {"name": "Smoke Ready", "values": [int(row.get(EXECUTION_GATE_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gate Records"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": EXECUTION_GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXECUTION_GATE_DOCTYPE, "width": 230},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 220},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "execution_gate_amount", "label": _("Gate Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "gated_payment_entry", "label": _("Gated Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "previous_gated_payment_entry", "label": _("Previous Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "next_smoke_payment_entry", "label": _("Next Smoke PE"), "fieldtype": "Data", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            execution_gate,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            execution_gate_amount,
            outstanding_amount,
            gated_payment_entry,
            previous_gated_payment_entry,
            next_smoke_payment_entry,
            detail
        FROM `tab{EXECUTION_GATE_ITEM_DOCTYPE}`
        WHERE gated_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": GATED_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Pass", "Warning", "Blocker", "Info"],
            "datasets": [
                {
                    "name": "Items",
                    "values": [
                        len([row for row in data if row.status == "Pass"]),
                        len([row for row in data if row.status == "Warning"]),
                        len([row for row in data if row.status == "Blocker"]),
                        len([row for row in data if row.status == "Info"]),
                    ],
                }
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Execution Gate Reference"]), "indicator": "Green", "label": _("Execution Gate References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_execution_gate_phase14o_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
