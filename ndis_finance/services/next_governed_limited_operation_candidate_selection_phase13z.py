import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


CANDIDATE_SELECTION_ACK = "I_CONFIRM_PHASE13Z_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_CANDIDATE_SELECTION_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"
CANDIDATE_SELECTION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection"
CANDIDATE_SELECTION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection Item"

DESIGN_READY_FIELD = "ready_for_next_governed_limited_op_candidate_selection"
CANDIDATE_SELECTION_READY_FIELD = "ready_for_next_governed_limited_op_candidate_validation"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
CANDIDATE_SELECTION_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 14
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 94
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_GL_ROWS = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00

CANDIDATE_SELECTION_SOURCE_DOCTYPE = "Sales Invoice"
CANDIDATE_SELECTION_REFERENCE_DOCTYPE = "Sales Invoice"
CANDIDATE_SELECTION_PARTY_TYPE = "Customer"


def make_candidate_selection_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-CANDIDATE-SELECTION-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    return count_dt(
        "GL Entry",
        {
            "voucher_type": "Payment Entry",
            "voucher_no": payment_entry,
            "is_cancelled": 1,
        },
    )


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


def latest_phase13y_design():
    filters = {
        "status": "Design Approved",
        "design_status": "Next Governed Limited Operation Design Approved",
        "design_approved": 1,
        "phase13x_planning_verified": 1,
        "planning_approved_verified": 1,
        "planning_payment_entry_verified": 1,
        "planning_payment_entry_cancelled_verified": 1,
        "planning_gl_rows_verified": 1,
        "planning_reversal_gl_rows_verified": 1,
        "planning_gl_net_zero_verified": 1,
        "planning_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "design_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
        "design_payment_entry_docstatus": 2,
        "design_payment_entry_status": "Cancelled",
        "design_source_doctype": CANDIDATE_SELECTION_SOURCE_DOCTYPE,
        "design_reference_doctype": CANDIDATE_SELECTION_REFERENCE_DOCTYPE,
        "design_party_type": CANDIDATE_SELECTION_PARTY_TYPE,
        "design_invoice_count": EXPECTED_INVOICE_COUNT,
        "design_total_amount": EXPECTED_TOTAL_AMOUNT,
        "design_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "design_gl_rows": EXPECTED_GL_ROWS,
        "design_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "design_gl_net": EXPECTED_GL_NET,
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

    if has_column(DESIGN_DOCTYPE, DESIGN_READY_FIELD):
        filters[DESIGN_READY_FIELD] = 1

    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "design_id",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "design_source_doctype",
            "design_reference_doctype",
            "design_party_type",
            "design_customer",
            "design_company",
            "design_currency",
            "design_invoice_names",
            "design_invoice_count",
            "design_total_amount",
            "design_restored_invoice_amount",
            "design_payment_entry",
            "design_payment_entry_docstatus",
            "design_payment_entry_status",
            "design_gl_rows",
            "design_reversal_gl_rows",
            "design_gl_net",
            "planning",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "candidate_validation",
            "candidate_selection",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_candidate_selection(design):
    rows = frappe.get_all(
        CANDIDATE_SELECTION_DOCTYPE,
        filters={
            "design": design,
            "status": "Candidate Selection Approved",
            "candidate_selection_approved": 1,
        },
        fields=["name", "candidate_selection_id", "candidate_selection_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def design_rows(design):
    rows = frappe.get_all(
        DESIGN_ITEM_DOCTYPE,
        filters={
            "design": design,
            "category": "Design Reference",
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
            "design_amount",
            "outstanding_amount",
            "gated_payment_entry",
            "design_payment_entry",
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
                    "candidate_selection_amount": flt(row.design_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "gated_payment_entry": row.gated_payment_entry,
                    "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def candidate_selection_total(rows):
    return flt(sum(flt(row.candidate_selection_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(design, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not design:
        issues.append("No approved Phase 13Y design found for candidate selection.")
        return issues

    existing = existing_approved_candidate_selection(design.name)
    if existing:
        issues.append(f"Approved Phase 13Z candidate selection already exists for this design: {existing.candidate_selection_id} / {existing.candidate_selection_payment_entry}")

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    state = payment_entry_state(CANDIDATE_SELECTION_PAYMENT_ENTRY)

    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")

    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")

    if not frappe.db.exists("Payment Entry", CANDIDATE_SELECTION_PAYMENT_ENTRY):
        issues.append(f"Candidate Selection Payment Entry does not exist: {CANDIDATE_SELECTION_PAYMENT_ENTRY}")

    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Candidate Selection Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Candidate Selection invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Candidate Selection invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")

    if candidate_selection_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Candidate Selection total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {candidate_selection_total(rows)}.")

    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_TOTAL_AMOUNT} before candidate selection.")

    if payment_entry_gl_rows(CANDIDATE_SELECTION_PAYMENT_ENTRY) != EXPECTED_GL_ROWS:
        issues.append(f"Candidate Selection Payment Entry must have {EXPECTED_GL_ROWS} GL rows.")

    if payment_entry_gl_net(CANDIDATE_SELECTION_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Candidate Selection Payment Entry GL net must be 0.00.")

    if int(design.design_reversal_gl_rows or 0) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append("Governed design reversal rows must remain the four-row delta.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 14 before candidate selection.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 94 before candidate selection.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before candidate selection.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before candidate selection.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before candidate selection.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before candidate selection.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for candidate selection.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for candidate selection.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for candidate selection.")

    return issues


def build_items(rows, issues, ack_ok):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Candidate Selection Source",
            "check_key": "candidate_selection_source_valid",
            "check_label": "Candidate selection source valid",
            "detail": f"Phase 13Y design evidence for {CANDIDATE_SELECTION_PAYMENT_ENTRY} is stable and ready for candidate selection approval.",
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Candidate Selection Source",
                "check_key": "candidate_selection_source_valid",
                "check_label": "Candidate selection source valid",
                "detail": issue,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
            })

    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Candidate Selection Reference",
            "check_key": "candidate_selection_sales_invoice_reference",
            "check_label": f"Candidate Selection Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} candidate selection amount={row.candidate_selection_amount}, outstanding={row.outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "candidate_selection_amount": row.candidate_selection_amount,
            "outstanding_amount": row.outstanding_amount,
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {CANDIDATE_SELECTION_ACK}",
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
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
        row = frappe.new_doc(CANDIDATE_SELECTION_ITEM_DOCTYPE)
        row.candidate_selection = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_candidate_selection_phase13z(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_candidate_selection_phase13z")

    design = latest_phase13y_design()
    rows = design_rows(design.name) if design else []

    guard_before = guardrails()
    ack_ok = acknowledgement == CANDIDATE_SELECTION_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

    source_issues = validate_source(design, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    state = payment_entry_state(CANDIDATE_SELECTION_PAYMENT_ENTRY)
    candidate_selection_gl_rows = payment_entry_gl_rows(CANDIDATE_SELECTION_PAYMENT_ENTRY)
    candidate_selection_gl_net = payment_entry_gl_net(CANDIDATE_SELECTION_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(CANDIDATE_SELECTION_PAYMENT_ENTRY)

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
        post_issues.append(f"Candidate selection must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Candidate selection must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Candidate selection must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after candidate selection.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after candidate selection.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during candidate selection. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and design
        and not post_issues
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and state.docstatus == 2
        and state.status == "Cancelled"
        and candidate_selection_gl_rows == EXPECTED_GL_ROWS
        and candidate_selection_gl_net == EXPECTED_GL_NET
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
        "status": "Candidate Selection Approved" if completed else "Needs Review",
        "candidate_selection_status": "Next Governed Limited Operation Candidate Selection Approved" if completed else "Needs Review",
        "candidate_selection_approved": completed,

        "phase13y_design_verified": 1 if design else 0,
        "design_approved_verified": 1 if design else 0,
        "design_payment_entry_verified": int(design and design.design_payment_entry == CANDIDATE_SELECTION_PAYMENT_ENTRY),
        "design_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "design_gl_rows_verified": int(candidate_selection_gl_rows == EXPECTED_GL_ROWS),
        "design_reversal_gl_rows_verified": int(design and int(design.design_reversal_gl_rows or 0) == EXPECTED_REVERSAL_GL_ROWS),
        "design_gl_net_zero_verified": int(candidate_selection_gl_net == EXPECTED_GL_NET),
        "design_restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),

        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,

        "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
        "candidate_selection_payment_entry_docstatus": state.docstatus,
        "candidate_selection_payment_entry_status": state.status,

        "candidate_selection_source_doctype": CANDIDATE_SELECTION_SOURCE_DOCTYPE,
        "candidate_selection_reference_doctype": CANDIDATE_SELECTION_REFERENCE_DOCTYPE,
        "candidate_selection_party_type": CANDIDATE_SELECTION_PARTY_TYPE,
        "candidate_selection_customer": unique_value(rows, "customer"),
        "candidate_selection_company": unique_value(rows, "company"),
        "candidate_selection_currency": unique_value(rows, "currency"),
        "candidate_selection_invoice_names": ", ".join(reference_names(rows)),
        "candidate_selection_invoice_count": len(rows),
        "candidate_selection_total_amount": candidate_selection_total(rows),
        "candidate_selection_restored_invoice_amount": restored_amount,

        "candidate_selection_gl_rows": candidate_selection_gl_rows,
        "candidate_selection_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "candidate_selection_gl_net": candidate_selection_gl_net,
        "candidate_selection_direct_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": design.target_policy if design else None,
        "target_policy_name": design.target_policy_name if design else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,

        CANDIDATE_SELECTION_READY_FIELD: completed,

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
        "candidate_validation": design.candidate_validation if design else None,
        "previous_candidate_selection": design.candidate_selection if design else None,

        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": CANDIDATE_SELECTION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 13Z approves next governed limited-operation candidate selection. No accounting movement occurs.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(CANDIDATE_SELECTION_DOCTYPE)
    doc.candidate_selection_id = make_candidate_selection_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = CANDIDATE_SELECTION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.candidate_selection_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "candidate_selection": doc.name,
        "candidate_selection_id": doc.candidate_selection_id,
        "candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_candidate_selection_phase13z_audit(candidate_selection, reason=None):
    assert_action("cancel_next_governed_limited_operation_candidate_selection_phase13z_audit")

    if not frappe.db.exists(CANDIDATE_SELECTION_DOCTYPE, candidate_selection):
        frappe.throw(_("Next governed limited-operation candidate selection audit not found: {0}").format(candidate_selection))

    doc = frappe.get_doc(CANDIDATE_SELECTION_DOCTYPE, candidate_selection)

    if doc.status == "Cancelled":
        return {"candidate_selection": candidate_selection, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_selection_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 13Z candidate selection record."))

    frappe.db.set_value(
        CANDIDATE_SELECTION_DOCTYPE,
        candidate_selection,
        {
            "status": "Cancelled",
            "candidate_selection_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 13Z no-ack candidate selection audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{CANDIDATE_SELECTION_ITEM_DOCTYPE}`
        SET status='Cancelled'
        WHERE candidate_selection=%(candidate_selection)s
        """,
        {"candidate_selection": candidate_selection},
    )

    frappe.db.commit()

    return {
        "candidate_selection": candidate_selection,
        "status": "Cancelled",
        "note": "No-ack candidate selection audit cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_candidate_selection_phase13z_summary(limit=20):
    return {
        "candidate_selection_records": frappe.get_all(
            CANDIDATE_SELECTION_DOCTYPE,
            filters={"candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY},
            fields=[
                "name",
                "candidate_selection_id",
                "status",
                "candidate_selection_status",
                "candidate_selection_approved",
                "gated_payment_entry",
                "gated_payment_entry_docstatus",
                "gated_payment_entry_status",
                "candidate_selection_payment_entry",
                "candidate_selection_payment_entry_docstatus",
                "candidate_selection_payment_entry_status",
                "candidate_selection_invoice_names",
                "candidate_selection_invoice_count",
                "candidate_selection_total_amount",
                "candidate_selection_restored_invoice_amount",
                "candidate_selection_gl_rows",
                "candidate_selection_reversal_gl_rows",
                "candidate_selection_gl_net",
                "candidate_selection_direct_cancelled_gl_rows",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                CANDIDATE_SELECTION_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            CANDIDATE_SELECTION_ITEM_DOCTYPE,
            filters={"candidate_selection_payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY},
            fields=[
                "name",
                "candidate_selection",
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
                "candidate_selection_amount",
                "outstanding_amount",
                "gated_payment_entry",
                "candidate_selection_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": CANDIDATE_SELECTION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 13Z next governed limited-operation candidate selection summary.",
    }


def execute_candidate_selection_phase13z_report(filters=None):
    columns = [
        {"fieldname": "candidate_selection", "label": _("Candidate Selection"), "fieldtype": "Link", "options": CANDIDATE_SELECTION_DOCTYPE, "width": 240},
        {"fieldname": "candidate_selection_id", "label": _("Candidate Selection ID"), "fieldtype": "Data", "width": 590},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "candidate_selection_status", "label": _("Candidate Selection Status"), "fieldtype": "Data", "width": 470},
        {"fieldname": "candidate_selection_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "candidate_selection_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "candidate_selection_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 115},
        {"fieldname": "candidate_selection_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "candidate_selection_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "candidate_selection_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "candidate_selection_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "candidate_selection_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "candidate_selection_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "candidate_selection_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": CANDIDATE_SELECTION_READY_FIELD, "label": _("Candidate Validation Ready"), "fieldtype": "Check", "width": 190},
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
            name AS candidate_selection,
            candidate_selection_id,
            status,
            candidate_selection_status,
            candidate_selection_approved,
            gated_payment_entry,
            candidate_selection_payment_entry,
            candidate_selection_payment_entry_docstatus,
            candidate_selection_payment_entry_status,
            candidate_selection_invoice_names,
            candidate_selection_total_amount,
            candidate_selection_restored_invoice_amount,
            candidate_selection_gl_rows,
            candidate_selection_reversal_gl_rows,
            candidate_selection_gl_net,
            `{CANDIDATE_SELECTION_READY_FIELD}` AS `{CANDIDATE_SELECTION_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{CANDIDATE_SELECTION_DOCTYPE}`
        WHERE candidate_selection_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY},
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.candidate_selection_id for row in data[:20]],
            "datasets": [
                {"name": "Candidate Selection Approved", "values": [int(row.candidate_selection_approved or 0) for row in data[:20]]},
                {"name": "Candidate Validation Ready", "values": [int(row.get(CANDIDATE_SELECTION_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Candidate Selection Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_selection_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CANDIDATE_SELECTION_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "candidate_selection", "label": _("Candidate Selection"), "fieldtype": "Link", "options": CANDIDATE_SELECTION_DOCTYPE, "width": 240},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 230},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "candidate_selection_amount", "label": _("Selection Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "candidate_selection_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            name AS item,
            candidate_selection,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            candidate_selection_amount,
            outstanding_amount,
            gated_payment_entry,
            candidate_selection_payment_entry,
            detail
        FROM `tab{CANDIDATE_SELECTION_ITEM_DOCTYPE}`
        WHERE candidate_selection_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": CANDIDATE_SELECTION_PAYMENT_ENTRY},
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
        {"value": len([row for row in data if row.category == "Candidate Selection Reference"]), "indicator": "Green", "label": _("Candidate Selection References"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_candidate_selection_phase13z_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
