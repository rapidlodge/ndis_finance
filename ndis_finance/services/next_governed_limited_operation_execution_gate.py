import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXECUTION_GATE_ACK = "I_CONFIRM_PHASE13E_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"
EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"

PREVIEW_READY_FIELD = "ready_for_next_governed_limited_op_execution_gate"
EXECUTION_GATE_READY_FIELD = "ready_for_next_governed_limited_op_smoke"

EXPECTED_MONITORED_PAYMENT_ENTRY = "ACC-PAY-2026-00013"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 12
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 78
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_VOUCHER_GL_NET = 0.00
EXPECTED_REVERSAL_GL_ROWS = 4

EXECUTION_SOURCE_DOCTYPE = "Sales Invoice"
EXECUTION_REFERENCE_DOCTYPE = "Sales Invoice"
EXECUTION_PARTY_TYPE = "Customer"
EXECUTION_PAYMENT_ENTRY_COUNT = 1
EXECUTION_GL_ENTRY_COUNT = 0
EXECUTION_PAYMENT_TYPE = "Receive"


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


def payment_entry_reversal_gl_rows(payment_entry):
    return max(0, int(payment_entry_gl_rows(payment_entry) or 0) - 4)


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


def latest_preview():
    filters = {
        "status": "Preview Approved",
        "preview_status": "Next Governed Limited Operation Preview Approved",
        "preview_approved": 1,
        "phase13c_candidate_validation_verified": 1,
        "candidate_validation_approved_verified": 1,
        "candidate_validation_source_verified": 1,
        "candidate_validation_reference_verified": 1,
        "candidate_validation_party_type_verified": 1,
        "candidate_validation_reference_set_locked_verified": 1,
        "candidate_validation_reference_set_verified": 1,
        "candidate_validation_shape_verified": 1,
        "candidate_validation_side_effects_blocked_verified": 1,
        "invoice_submission_verified": 1,
        "invoice_outstanding_verified": 1,
        "preview_source_locked": 1,
        "preview_shape_locked": 1,
        "preview_reference_set_locked": 1,
        "preview_reference_set_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "previewed_source_doctype": EXECUTION_SOURCE_DOCTYPE,
        "previewed_reference_doctype": EXECUTION_REFERENCE_DOCTYPE,
        "previewed_party_type": EXECUTION_PARTY_TYPE,
        "previewed_invoice_count": EXPECTED_INVOICE_COUNT,
        "previewed_total_amount": EXPECTED_TOTAL_AMOUNT,
        "previewed_payment_entry_count": EXECUTION_PAYMENT_ENTRY_COUNT,
        "previewed_gl_entry_count": EXECUTION_GL_ENTRY_COUNT,
        "previewed_live_posting_allowed": 0,
        "previewed_journal_entry_side_effect_allowed": 0,
        "previewed_purchase_invoice_side_effect_allowed": 0,
        "previewed_payment_type": EXECUTION_PAYMENT_TYPE,
        "previewed_posting_allowed": 0,
        "previewed_submit_allowed": 0,
        "previewed_cancel_allowed": 0,
        "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        "monitored_payment_entry_docstatus": 2,
        "monitored_payment_entry_status": "Cancelled",
        "monitored_voucher_gl_rows": EXPECTED_VOUCHER_GL_ROWS,
        "monitored_voucher_gl_net": EXPECTED_VOUCHER_GL_NET,
        "monitored_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "monitored_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
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

    fields = [
        "name",
        "preview_id",
        "previewed_source_doctype",
        "previewed_reference_doctype",
        "previewed_party_type",
        "previewed_customer",
        "previewed_company",
        "previewed_currency",
        "previewed_invoice_names",
        "previewed_invoice_count",
        "previewed_total_amount",
        "previewed_payment_entry_count",
        "previewed_gl_entry_count",
        "previewed_live_posting_allowed",
        "previewed_journal_entry_side_effect_allowed",
        "previewed_purchase_invoice_side_effect_allowed",
        "previewed_payment_type",
        "previewed_party",
        "previewed_posting_allowed",
        "previewed_submit_allowed",
        "previewed_cancel_allowed",
        "preview_reference_set_locked",
        "preview_reference_set_verified",
        "monitored_payment_entry",
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
    ]

    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters=filters,
        fields=fields,
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
        },
        fields=["name", "execution_gate_id", "execution_invoice_names"],
        limit=1,
    )
    return rows[0] if rows else None


def preview_rows(preview):
    rows = frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        filters={
            "preview": preview,
            "category": "Previewed Reference",
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
            "previewed_amount",
            "current_outstanding_amount",
            "invoice_docstatus",
            "outstanding_sufficient",
            "monitored_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        si = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
            ["docstatus", "customer", "company", "currency", "outstanding_amount"],
            as_dict=True,
        ) if frappe.db.exists("Sales Invoice", row.reference_name) else None

        amount = flt(row.previewed_amount or 0, 2)
        outstanding = flt((si.outstanding_amount if si else row.current_outstanding_amount) or 0, 2)

        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "execution_amount": amount,
                    "current_outstanding_amount": outstanding,
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else int(row.invoice_docstatus or 0),
                    "outstanding_sufficient": int(outstanding >= amount and amount > 0),
                    "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def execution_total(rows):
    return flt(sum(flt(row.execution_amount or 0, 2) for row in rows), 2)


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


def validate_source(preview, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not preview:
        issues.append("No approved Phase 13D preview found for execution gate.")
        return issues

    existing = existing_approved_execution_gate(preview.name)
    if existing:
        issues.append(f"Approved Phase 13E execution gate already exists for this preview: {existing.execution_gate_id} / {existing.execution_invoice_names}")

    pe_state = payment_entry_state(EXPECTED_MONITORED_PAYMENT_ENTRY)

    if preview.monitored_payment_entry != EXPECTED_MONITORED_PAYMENT_ENTRY:
        issues.append(f"Monitored Payment Entry must be {EXPECTED_MONITORED_PAYMENT_ENTRY}.")

    if pe_state.docstatus != 2:
        issues.append(f"Monitored Payment Entry must remain cancelled. docstatus={pe_state.docstatus}")

    if pe_state.status != "Cancelled":
        issues.append(f"Monitored Payment Entry status must remain Cancelled. status={pe_state.status}")

    if preview.previewed_source_doctype != EXECUTION_SOURCE_DOCTYPE:
        issues.append("Preview source DocType changed.")

    if preview.previewed_reference_doctype != EXECUTION_REFERENCE_DOCTYPE:
        issues.append("Preview reference DocType changed.")

    if preview.previewed_party_type != EXECUTION_PARTY_TYPE:
        issues.append("Preview party type changed.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Execution invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Execution invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")

    if execution_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Execution total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {execution_total(rows)}.")

    if int(preview.previewed_payment_entry_count or 0) != EXECUTION_PAYMENT_ENTRY_COUNT:
        issues.append("Execution future Payment Entry count must remain 1.")

    if int(preview.previewed_gl_entry_count or 0) != EXECUTION_GL_ENTRY_COUNT:
        issues.append("Execution future GL Entry count must remain 0 at gate stage.")

    if int(preview.previewed_live_posting_allowed or 0) != 0:
        issues.append("Execution live posting allowed must remain 0 at gate stage.")

    if int(preview.previewed_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Execution Journal Entry side effect allowed must remain 0.")

    if int(preview.previewed_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Execution Purchase Invoice side effect allowed must remain 0.")

    if int(preview.previewed_posting_allowed or 0) != 0:
        issues.append("Preview posting allowed must remain 0 before smoke.")

    if int(preview.previewed_submit_allowed or 0) != 0:
        issues.append("Preview submit allowed must remain 0 before smoke.")

    if int(preview.previewed_cancel_allowed or 0) != 0:
        issues.append("Preview cancel allowed must remain 0 before smoke.")

    if not same_value_verified(rows, "customer"):
        issues.append("Execution Sales Invoices must share the same customer.")

    if not same_value_verified(rows, "company"):
        issues.append("Execution Sales Invoices must share the same company.")

    if not same_value_verified(rows, "currency"):
        issues.append("Execution Sales Invoices must share the same currency.")

    if not invoices_submitted(rows):
        issues.append("All execution Sales Invoices must remain submitted.")

    if not invoices_outstanding_sufficient(rows):
        issues.append("All execution Sales Invoices must have sufficient outstanding amount.")

    if payment_entry_gl_rows(EXPECTED_MONITORED_PAYMENT_ENTRY) != EXPECTED_VOUCHER_GL_ROWS:
        issues.append(f"Monitored Payment Entry voucher GL rows must remain {EXPECTED_VOUCHER_GL_ROWS}.")

    if payment_entry_reversal_gl_rows(EXPECTED_MONITORED_PAYMENT_ENTRY) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append(f"Monitored Payment Entry reversal GL rows must remain {EXPECTED_REVERSAL_GL_ROWS}.")

    if payment_entry_gl_net(EXPECTED_MONITORED_PAYMENT_ENTRY) != EXPECTED_VOUCHER_GL_NET:
        issues.append("Monitored Payment Entry GL net must remain 0.00.")

    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must remain {EXPECTED_TOTAL_AMOUNT}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 12 before execution gate.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 78 before execution gate.")

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
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    return issues


def build_items(rows, issues, ack_ok, completed=0):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Execution Gate Source",
            "check_key": "execution_gate_source_valid",
            "check_label": "Execution gate source valid",
            "detail": f"Phase 13D preview for {EXPECTED_MONITORED_PAYMENT_ENTRY} is stable and can open smoke execution.",
            "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Execution Gate Source",
                "check_key": "execution_gate_source_valid",
                "check_label": "Execution gate source valid",
                "detail": issue,
                "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
            })

    for row in rows:
        items.append({
            "status": "Pass" if int(row.outstanding_sufficient or 0) == 1 else "Blocker",
            "severity": "High",
            "category": "Execution Reference",
            "check_key": "execution_sales_invoice_reference",
            "check_label": f"Execution Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} execution amount={row.execution_amount}, current outstanding={row.current_outstanding_amount}, sufficient={row.outstanding_sufficient}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "execution_amount": row.execution_amount,
            "current_outstanding_amount": row.current_outstanding_amount,
            "invoice_docstatus": row.invoice_docstatus,
            "outstanding_sufficient": row.outstanding_sufficient,
            "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        })

    checks = [
        ("execution_gate_source", "Execution source/reference/party", f"{EXECUTION_SOURCE_DOCTYPE} / {EXECUTION_REFERENCE_DOCTYPE} / {EXECUTION_PARTY_TYPE}"),
        ("execution_gate_shape", "Execution gate shape", f"{EXPECTED_INVOICE_COUNT} / {EXPECTED_TOTAL_AMOUNT} / {EXECUTION_PAYMENT_ENTRY_COUNT} / {EXECUTION_GL_ENTRY_COUNT}"),
        ("execution_gate_side_effects", "Execution live/JE/PI side effects", "0 / 0 / 0"),
        ("smoke_ready", "Ready for next governed smoke", completed),
    ]

    for key, label, value in checks:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Execution Gate Evidence",
            "check_key": key,
            "check_label": label,
            "detail": f"value={value}",
            "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {EXECUTION_GATE_ACK}",
        "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
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
        if item.get("category") != "Execution Reference":
            continue
        row = frappe.new_doc(EXECUTION_GATE_ITEM_DOCTYPE)
        row.execution_gate = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_execution_gate")

    preview = latest_preview()
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

    pe_state = payment_entry_state(EXPECTED_MONITORED_PAYMENT_ENTRY)
    voucher_rows = payment_entry_gl_rows(EXPECTED_MONITORED_PAYMENT_ENTRY)
    voucher_net = payment_entry_gl_net(EXPECTED_MONITORED_PAYMENT_ENTRY)
    reversal_rows = payment_entry_reversal_gl_rows(EXPECTED_MONITORED_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)

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
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during execution gate. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and preview
        and not post_issues
        and pe_state.docstatus == 2
        and pe_state.status == "Cancelled"
        and reference_names(rows) == EXPECTED_INVOICES
        and execution_total(rows) == EXPECTED_TOTAL_AMOUNT
        and invoices_submitted(rows) == 1
        and invoices_outstanding_sufficient(rows) == 1
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == EXPECTED_VOUCHER_GL_NET
        and reversal_rows == EXPECTED_REVERSAL_GL_ROWS
        and restored_amount == EXPECTED_TOTAL_AMOUNT
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT
        and actual_pe_created == 0
        and actual_pe_cancelled == 0
        and actual_gl_created == 0
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok, completed=completed)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_status": "Next Governed Limited Operation Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_approved": completed,

        "phase13d_preview_verified": 1 if preview else 0,
        "preview_approved_verified": 1 if preview else 0,
        "preview_source_verified": int(preview and preview.previewed_source_doctype == EXECUTION_SOURCE_DOCTYPE),
        "preview_reference_verified": int(preview and preview.previewed_reference_doctype == EXECUTION_REFERENCE_DOCTYPE),
        "preview_party_type_verified": int(preview and preview.previewed_party_type == EXECUTION_PARTY_TYPE),
        "preview_reference_set_locked_verified": int(row_get(preview, "preview_reference_set_locked", 0) == 1) if preview and has_column(PREVIEW_DOCTYPE, "preview_reference_set_locked") else int(reference_names(rows) == EXPECTED_INVOICES),
        "preview_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "preview_shape_verified": int(
            len(rows) == EXPECTED_INVOICE_COUNT
            and execution_total(rows) == EXPECTED_TOTAL_AMOUNT
            and preview
            and int(preview.previewed_payment_entry_count or 0) == EXECUTION_PAYMENT_ENTRY_COUNT
            and int(preview.previewed_gl_entry_count or 0) == EXECUTION_GL_ENTRY_COUNT
        ),
        "preview_side_effects_blocked_verified": int(
            preview
            and int(preview.previewed_live_posting_allowed or 0) == 0
            and int(preview.previewed_journal_entry_side_effect_allowed or 0) == 0
            and int(preview.previewed_purchase_invoice_side_effect_allowed or 0) == 0
            and int(preview.previewed_posting_allowed or 0) == 0
            and int(preview.previewed_submit_allowed or 0) == 0
            and int(preview.previewed_cancel_allowed or 0) == 0
        ),
        "invoice_submission_verified": invoices_submitted(rows),
        "invoice_outstanding_verified": invoices_outstanding_sufficient(rows),
        "execution_gate_source_locked": completed,
        "execution_gate_shape_locked": completed,
        "execution_gate_reference_set_locked": completed,
        "execution_gate_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "execution_gate_smoke_allowed": completed,
        "execution_gate_live_posting_blocked": int(policy_live_after == 0 and config["live_pe_enabled"] == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),

        "execution_source_doctype": EXECUTION_SOURCE_DOCTYPE,
        "execution_reference_doctype": EXECUTION_REFERENCE_DOCTYPE,
        "execution_party_type": EXECUTION_PARTY_TYPE,
        "execution_customer": unique_value(rows, "customer"),
        "execution_company": unique_value(rows, "company"),
        "execution_currency": unique_value(rows, "currency"),
        "execution_invoice_names": ", ".join(reference_names(rows)),
        "execution_invoice_count": len(rows),
        "execution_total_amount": execution_total(rows),
        "execution_payment_entry_count": EXECUTION_PAYMENT_ENTRY_COUNT,
        "execution_gl_entry_count": EXECUTION_GL_ENTRY_COUNT,
        "execution_live_posting_allowed": 0,
        "execution_journal_entry_side_effect_allowed": 0,
        "execution_purchase_invoice_side_effect_allowed": 0,

        "execution_payment_type": EXECUTION_PAYMENT_TYPE,
        "execution_party": unique_value(rows, "customer"),
        "execution_posting_allowed": 0,
        "execution_submit_allowed": 0,
        "execution_cancel_allowed": 0,

        "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        "monitored_payment_entry_docstatus": pe_state.docstatus,
        "monitored_payment_entry_status": pe_state.status,
        "monitored_voucher_gl_rows": voucher_rows,
        "monitored_voucher_gl_net": voucher_net,
        "monitored_reversal_gl_rows": reversal_rows,
        "monitored_restored_invoice_amount": restored_amount,

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
        "candidate_validation": preview.candidate_validation if preview else None,
        "candidate_selection": preview.candidate_selection if preview else None,
        "design": preview.design if preview else None,
        "planning": preview.planning if preview else None,
        "monitor": preview.monitor if preview else None,
        "baseline": preview.baseline if preview else None,
        "closeout": preview.closeout if preview else None,
        "freeze": preview.freeze if preview else None,
        "rollback": preview.rollback if preview else None,
        "smoke": preview.smoke if preview else None,
        "previous_execution_gate": None,

        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 13E approves the next governed limited-operation execution gate only. No accounting movement occurs.",
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

    return {
        **result,
        "created": True,
        "execution_gate": doc.name,
        "execution_gate_id": doc.execution_gate_id,
        "monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_execution_gate_audit(execution_gate, reason=None):
    assert_action("cancel_next_governed_limited_operation_execution_gate_audit")

    if not frappe.db.exists(EXECUTION_GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Next governed limited-operation execution gate audit not found: {0}").format(execution_gate))

    doc = frappe.get_doc(EXECUTION_GATE_DOCTYPE, execution_gate)

    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 13E execution gate record."))

    frappe.db.set_value(
        EXECUTION_GATE_DOCTYPE,
        execution_gate,
        {
            "status": "Cancelled",
            "execution_gate_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 13E no-ack execution gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{EXECUTION_GATE_ITEM_DOCTYPE}`
        SET status='Cancelled'
        WHERE execution_gate=%(execution_gate)s
        """,
        {"execution_gate": execution_gate},
    )

    frappe.db.commit()

    return {
        "execution_gate": execution_gate,
        "status": "Cancelled",
        "note": "No-ack execution gate audit cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_execution_gate_summary(limit=20):
    return {
        "execution_gate_records": frappe.get_all(
            EXECUTION_GATE_DOCTYPE,
            filters={"monitored_payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY},
            fields=[
                "name",
                "execution_gate_id",
                "status",
                "execution_gate_status",
                "execution_gate_approved",
                "execution_source_doctype",
                "execution_reference_doctype",
                "execution_party_type",
                "execution_invoice_names",
                "execution_invoice_count",
                "execution_total_amount",
                "execution_payment_entry_count",
                "execution_gl_entry_count",
                "execution_live_posting_allowed",
                "execution_journal_entry_side_effect_allowed",
                "execution_purchase_invoice_side_effect_allowed",
                "execution_payment_type",
                "execution_party",
                "execution_posting_allowed",
                "execution_submit_allowed",
                "execution_cancel_allowed",
                "monitored_payment_entry",
                "monitored_payment_entry_docstatus",
                "monitored_payment_entry_status",
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
                "execution_amount",
                "current_outstanding_amount",
                "invoice_docstatus",
                "outstanding_sufficient",
                "monitored_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 13E next governed limited-operation execution gate summary.",
    }


def execute_execution_gate_report(filters=None):
    columns = [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXECUTION_GATE_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 540},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "execution_gate_status", "label": _("Execution Status"), "fieldtype": "Data", "width": 440},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "execution_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "execution_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "execution_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "execution_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "execution_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 105},
        {"fieldname": "execution_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "execution_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "execution_gl_entry_count", "label": _("Future GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": EXECUTION_GATE_READY_FIELD, "label": _("Smoke Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
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
            execution_source_doctype,
            execution_reference_doctype,
            execution_party_type,
            execution_invoice_names,
            execution_invoice_count,
            execution_total_amount,
            execution_payment_entry_count,
            execution_gl_entry_count,
            `{EXECUTION_GATE_READY_FIELD}` AS `{EXECUTION_GATE_READY_FIELD}`,
            monitored_payment_entry,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{EXECUTION_GATE_DOCTYPE}`
        WHERE monitored_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": EXPECTED_MONITORED_PAYMENT_ENTRY},
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
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXECUTION_GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 220},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "execution_amount", "label": _("Execution Amount"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "current_outstanding_amount", "label": _("Current Outstanding"), "fieldtype": "Currency", "width": 145},
        {"fieldname": "invoice_docstatus", "label": _("Invoice Docstatus"), "fieldtype": "Int", "width": 120},
        {"fieldname": "outstanding_sufficient", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
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
            execution_amount,
            current_outstanding_amount,
            invoice_docstatus,
            outstanding_sufficient,
            monitored_payment_entry,
            check_label,
            detail
        FROM `tab{EXECUTION_GATE_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
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
        {"value": len([row for row in data if row.category == "Execution Reference"]), "indicator": "Green", "label": _("Execution References"), "datatype": "Int"},
        {"value": len([row for row in data if int(row.outstanding_sufficient or 0) == 1]), "indicator": "Green", "label": _("Outstanding OK"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_execution_gate_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
