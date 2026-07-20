import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE14B_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_PREVIEW_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CANDIDATE_VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation"
CANDIDATE_VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation Item"
PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"

CANDIDATE_VALIDATION_READY_FIELD = "ready_for_next_governed_limited_op_preview"
PREVIEW_READY_FIELD = "ready_for_next_governed_limited_op_execution_gate"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
PREVIEW_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 14
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 94
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_PREVIEW_GL_ROWS = 8
EXPECTED_PREVIEW_REVERSAL_GL_ROWS = 4
EXPECTED_PREVIEW_GL_NET = 0.00

PREVIEW_SOURCE_DOCTYPE = "Sales Invoice"
PREVIEW_REFERENCE_DOCTYPE = "Sales Invoice"
PREVIEW_PARTY_TYPE = "Customer"


def make_preview_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not has_column("GL Entry", "is_cancelled"):
        return 0
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


def existing_link(doctype, name):
    if name and frappe.db.exists(doctype, name):
        return name
    return None


def latest_phase14a_candidate_validation():
    filters = {
        "status": "Candidate Validation Approved",
        "candidate_validation_status": "Next Governed Limited Operation Candidate Validation Approved",
        "candidate_validation_approved": 1,
        "phase13z_candidate_selection_verified": 1,
        "candidate_selection_approved_verified": 1,
        "candidate_selection_payment_entry_verified": 1,
        "candidate_selection_payment_entry_cancelled_verified": 1,
        "candidate_selection_gl_rows_verified": 1,
        "candidate_selection_reversal_gl_rows_verified": 1,
        "candidate_selection_gl_net_zero_verified": 1,
        "candidate_selection_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "candidate_validation_payment_entry": PREVIEW_PAYMENT_ENTRY,
        "candidate_validation_payment_entry_docstatus": 2,
        "candidate_validation_payment_entry_status": "Cancelled",
        "candidate_validation_source_doctype": PREVIEW_SOURCE_DOCTYPE,
        "candidate_validation_reference_doctype": PREVIEW_REFERENCE_DOCTYPE,
        "candidate_validation_party_type": PREVIEW_PARTY_TYPE,
        "candidate_validation_invoice_count": EXPECTED_INVOICE_COUNT,
        "candidate_validation_total_amount": EXPECTED_TOTAL_AMOUNT,
        "candidate_validation_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "candidate_validation_gl_rows": EXPECTED_PREVIEW_GL_ROWS,
        "candidate_validation_reversal_gl_rows": EXPECTED_PREVIEW_REVERSAL_GL_ROWS,
        "candidate_validation_gl_net": EXPECTED_PREVIEW_GL_NET,
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
    if has_column(CANDIDATE_VALIDATION_DOCTYPE, CANDIDATE_VALIDATION_READY_FIELD):
        filters[CANDIDATE_VALIDATION_READY_FIELD] = 1

    rows = frappe.get_all(
        CANDIDATE_VALIDATION_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "candidate_validation_id",
            "candidate_validation_source_doctype",
            "candidate_validation_reference_doctype",
            "candidate_validation_party_type",
            "candidate_validation_customer",
            "candidate_validation_company",
            "candidate_validation_currency",
            "candidate_validation_invoice_names",
            "candidate_validation_invoice_count",
            "candidate_validation_total_amount",
            "candidate_validation_restored_invoice_amount",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "candidate_validation_payment_entry",
            "candidate_validation_payment_entry_docstatus",
            "candidate_validation_payment_entry_status",
            "candidate_validation_gl_rows",
            "candidate_validation_reversal_gl_rows",
            "candidate_validation_gl_net",
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
            "preview",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_preview(candidate_validation):
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={"candidate_validation": candidate_validation, "status": "Preview Approved", "preview_approved": 1},
        fields=["name", "preview_id", "preview_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def candidate_validation_rows(candidate_validation):
    rows = frappe.get_all(
        CANDIDATE_VALIDATION_ITEM_DOCTYPE,
        filters={
            "candidate_validation": candidate_validation,
            "category": "Candidate Validation Reference",
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
            "candidate_validation_amount",
            "outstanding_amount",
            "candidate_validation_payment_entry",
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
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "preview_amount": flt(row.candidate_validation_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                    "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def preview_total(rows):
    return flt(sum(flt(row.preview_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(candidate_validation, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not candidate_validation:
        issues.append("No approved Phase 14A candidate validation found for preview.")
        return issues
    existing = existing_approved_preview(candidate_validation.name)
    if existing:
        issues.append(f"Approved Phase 14B preview already exists for this candidate validation: {existing.preview_id} / {existing.preview_payment_entry}")

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    state = payment_entry_state(PREVIEW_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", PREVIEW_PAYMENT_ENTRY):
        issues.append(f"Preview Payment Entry does not exist: {PREVIEW_PAYMENT_ENTRY}")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Preview Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Preview invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Preview invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if preview_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Preview total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {preview_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_TOTAL_AMOUNT} before preview.")
    if payment_entry_gl_rows(PREVIEW_PAYMENT_ENTRY) != EXPECTED_PREVIEW_GL_ROWS:
        issues.append(f"Preview Payment Entry must have {EXPECTED_PREVIEW_GL_ROWS} GL rows.")
    if payment_entry_gl_net(PREVIEW_PAYMENT_ENTRY) != EXPECTED_PREVIEW_GL_NET:
        issues.append("Preview Payment Entry GL net must be 0.00.")
    if int(candidate_validation.candidate_validation_reversal_gl_rows or 0) != EXPECTED_PREVIEW_REVERSAL_GL_ROWS:
        issues.append("Governed candidate validation reversal rows must remain the four-row delta.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 14 before preview.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 94 before preview.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before preview.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before preview.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before preview.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before preview.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for preview.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for preview.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for preview.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Preview Source",
            "check_key": "preview_source_valid",
            "check_label": "Preview source valid",
            "detail": f"Phase 14A candidate-validation evidence for {PREVIEW_PAYMENT_ENTRY} is stable and ready for preview approval.",
            "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Preview Source",
                "check_key": "preview_source_valid",
                "check_label": "Preview source valid",
                "detail": issue,
                "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
            })
    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Preview Reference",
            "check_key": "preview_sales_invoice_reference",
            "check_label": f"Preview Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} preview amount={row.preview_amount}, outstanding={row.outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "preview_amount": row.preview_amount,
            "outstanding_amount": row.outstanding_amount,
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
        })
    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {PREVIEW_ACK}",
        "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
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
        row = frappe.new_doc(PREVIEW_ITEM_DOCTYPE)
        row.preview = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_preview_phase14b(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_preview_phase14b")
    candidate_validation = latest_phase14a_candidate_validation()
    rows = candidate_validation_rows(candidate_validation.name) if candidate_validation else []
    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, candidate_validation.target_policy, "production_batch_enabled") if candidate_validation else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, candidate_validation.target_policy, "live_posting_allowed") if candidate_validation else 0
    source_issues = validate_source(candidate_validation, rows, guard_before, config, policy_enabled_before, policy_live_before)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, candidate_validation.target_policy, "production_batch_enabled") if candidate_validation else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, candidate_validation.target_policy, "live_posting_allowed") if candidate_validation else 0

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    state = payment_entry_state(PREVIEW_PAYMENT_ENTRY)
    preview_gl_rows = payment_entry_gl_rows(PREVIEW_PAYMENT_ENTRY)
    preview_gl_net = payment_entry_gl_net(PREVIEW_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(PREVIEW_PAYMENT_ENTRY)
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
        post_issues.append(f"Preview must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Preview must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Preview must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after preview.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after preview.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during preview. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and candidate_validation
        and not post_issues
        and state.docstatus == 2
        and state.status == "Cancelled"
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and preview_gl_rows == EXPECTED_PREVIEW_GL_ROWS
        and preview_gl_net == EXPECTED_PREVIEW_GL_NET
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
    items = build_items(rows, post_issues, ack_ok)
    item_summary = summarise_items(items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Preview Approved" if completed else "Needs Review",
        "preview_status": "Next Governed Limited Operation Preview Approved" if completed else "Needs Review",
        "preview_approved": completed,
        "phase14a_candidate_validation_verified": 1 if candidate_validation else 0,
        "candidate_validation_approved_verified": 1 if candidate_validation else 0,
        "candidate_validation_payment_entry_verified": int(candidate_validation and candidate_validation.candidate_validation_payment_entry == PREVIEW_PAYMENT_ENTRY),
        "candidate_validation_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "candidate_validation_gl_rows_verified": int(preview_gl_rows == EXPECTED_PREVIEW_GL_ROWS),
        "candidate_validation_reversal_gl_rows_verified": int(candidate_validation and int(candidate_validation.candidate_validation_reversal_gl_rows or 0) == EXPECTED_PREVIEW_REVERSAL_GL_ROWS),
        "candidate_validation_gl_net_zero_verified": int(preview_gl_net == EXPECTED_PREVIEW_GL_NET),
        "candidate_validation_restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "preview_payment_entry": PREVIEW_PAYMENT_ENTRY,
        "preview_payment_entry_docstatus": state.docstatus,
        "preview_payment_entry_status": state.status,
        "preview_source_doctype": PREVIEW_SOURCE_DOCTYPE,
        "preview_reference_doctype": PREVIEW_REFERENCE_DOCTYPE,
        "preview_party_type": PREVIEW_PARTY_TYPE,
        "preview_customer": unique_value(rows, "customer"),
        "preview_company": unique_value(rows, "company"),
        "preview_currency": unique_value(rows, "currency"),
        "preview_invoice_names": ", ".join(reference_names(rows)),
        "preview_invoice_count": len(rows),
        "preview_total_amount": preview_total(rows),
        "preview_restored_invoice_amount": restored_amount,
        "preview_gl_rows": preview_gl_rows,
        "preview_reversal_gl_rows": EXPECTED_PREVIEW_REVERSAL_GL_ROWS,
        "preview_gl_net": preview_gl_net,
        "preview_direct_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": candidate_validation.target_policy if candidate_validation else None,
        "target_policy_name": candidate_validation.target_policy_name if candidate_validation else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        PREVIEW_READY_FIELD: completed,
        "candidate_validation": existing_link(CANDIDATE_VALIDATION_DOCTYPE, candidate_validation.name) if candidate_validation else None,
        "candidate_selection": existing_link("NDIS Next Governed Limited Op Candidate Selection", candidate_validation.candidate_selection) if candidate_validation else None,
        "design": existing_link("NDIS Next Governed Limited Op Design", candidate_validation.design) if candidate_validation else None,
        "planning": existing_link("NDIS Next Governed Limited Op Planning", candidate_validation.planning) if candidate_validation else None,
        "monitor": existing_link("NDIS Next Governed Limited Op Runtime Monitor", candidate_validation.monitor) if candidate_validation else None,
        "baseline": existing_link("NDIS Next Governed Limited Op Steady Baseline", candidate_validation.baseline) if candidate_validation else None,
        "closeout": existing_link("NDIS Next Governed Limited Op Closeout", candidate_validation.closeout) if candidate_validation else None,
        "freeze": existing_link("NDIS Next Governed Limited Op Rollback Freeze", candidate_validation.freeze) if candidate_validation else None,
        "rollback": existing_link("NDIS Next Governed Limited Op Smoke Rollback", candidate_validation.rollback) if candidate_validation else None,
        "smoke": existing_link("NDIS Next Governed Limited Op Smoke", candidate_validation.smoke) if candidate_validation else None,
        "execution_gate": existing_link("NDIS Next Governed Limited Op Execution Gate", candidate_validation.execution_gate) if candidate_validation else None,
        "previous_preview": existing_link(PREVIEW_DOCTYPE, candidate_validation.preview) if candidate_validation else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 14B approves next governed limited-operation preview. No accounting movement occurs.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.preview_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "preview": doc.name, "preview_id": doc.preview_id, "preview_payment_entry": PREVIEW_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_preview_phase14b_audit(preview, reason=None):
    assert_action("cancel_next_governed_limited_operation_preview_phase14b_audit")
    if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
        frappe.throw(_("Next governed limited-operation preview audit not found: {0}").format(preview))
    doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)
    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.preview_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 14B preview record."))
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        preview,
        {"status": "Cancelled", "preview_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 14B no-ack preview audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{PREVIEW_ITEM_DOCTYPE}` SET status='Cancelled' WHERE preview=%(preview)s", {"preview": preview})
    frappe.db.commit()
    return {"preview": preview, "status": "Cancelled", "note": "No-ack preview audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_preview_phase14b_summary(limit=20):
    return {
        "preview_records": frappe.get_all(
            PREVIEW_DOCTYPE,
            filters={"preview_payment_entry": PREVIEW_PAYMENT_ENTRY},
            fields=[
                "name", "preview_id", "status", "preview_status", "preview_approved", "preview_payment_entry",
                "preview_payment_entry_docstatus", "preview_payment_entry_status", "preview_invoice_names",
                "preview_invoice_count", "preview_total_amount", "preview_restored_invoice_amount",
                "preview_gl_rows", "preview_reversal_gl_rows", "preview_gl_net", "payment_entry_count_before",
                "payment_entry_count_after", "payment_entry_gl_count_before", "payment_entry_gl_count_after",
                "actual_payment_entry_created_count", "actual_payment_entry_cancelled_count", "actual_gl_created_count",
                "submitted_journal_entry_count_today", "purchase_invoice_count_today", PREVIEW_READY_FIELD,
                "checked_on", "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            PREVIEW_ITEM_DOCTYPE,
            filters={"preview_payment_entry": PREVIEW_PAYMENT_ENTRY},
            fields=[
                "name", "preview", "status", "severity", "category", "check_key", "check_label", "line_no",
                "reference_doctype", "reference_name", "customer", "company", "currency", "preview_amount",
                "outstanding_amount", "gated_payment_entry", "preview_payment_entry", "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14B next governed limited-operation preview summary.",
    }


def execute_preview_phase14b_report(filters=None):
    columns = [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 540},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 420},
        {"fieldname": "preview_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "preview_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "preview_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "preview_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "preview_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "preview_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "preview_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "preview_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "preview_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": PREVIEW_READY_FIELD, "label": _("Execution Gate Ready"), "fieldtype": "Check", "width": 165},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS preview, preview_id, status, preview_status, preview_approved, preview_payment_entry,
            preview_payment_entry_docstatus, preview_payment_entry_status, preview_invoice_names,
            gated_payment_entry,
            preview_total_amount, preview_restored_invoice_amount, preview_gl_rows, preview_reversal_gl_rows,
            preview_gl_net, `{PREVIEW_READY_FIELD}` AS `{PREVIEW_READY_FIELD}`, payment_entry_count_before,
            payment_entry_count_after, payment_entry_gl_count_before, payment_entry_gl_count_after,
            actual_gl_created_count, checked_on
        FROM `tab{PREVIEW_DOCTYPE}`
        WHERE preview_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": PREVIEW_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.preview_id for row in data[:20]],
            "datasets": [
                {"name": "Preview Approved", "values": [int(row.preview_approved or 0) for row in data[:20]]},
                {"name": "Execution Gate Ready", "values": [int(row.get(PREVIEW_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Preview Records"), "datatype": "Int"},
        {"value": sum(int(row.preview_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PREVIEW_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "preview_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "preview_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS item, preview, status, category, line_no, reference_doctype, reference_name,
            preview_amount, outstanding_amount, gated_payment_entry, preview_payment_entry, detail
        FROM `tab{PREVIEW_ITEM_DOCTYPE}`
        WHERE preview_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": PREVIEW_PAYMENT_ENTRY},
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
        {"value": len([row for row in data if row.category == "Preview Reference"]), "indicator": "Green", "label": _("Preview References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_phase14b_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
