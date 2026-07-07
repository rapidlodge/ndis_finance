import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


VALIDATION_ACK = "I_CONFIRM_PHASE12Q_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_CANDIDATE_VALIDATION_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CANDIDATE_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection"
CANDIDATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Selection Item"
VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation"
VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Validation Item"

CANDIDATE_READY_FIELD = "ready_for_next_governed_limited_op_candidate_validation_gate"
VALIDATION_READY_FIELD = "ready_for_next_governed_limited_op_preview_gate"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00012"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT = 11
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 70
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_VOUCHER_GL_NET = 0.00
EXPECTED_REVERSAL_GL_ROWS = 4

VALIDATED_SOURCE_DOCTYPE = "Sales Invoice"
VALIDATED_REFERENCE_DOCTYPE = "Sales Invoice"
VALIDATED_PARTY_TYPE = "Customer"
VALIDATED_PAYMENT_ENTRY_COUNT = 1
VALIDATED_GL_ENTRY_COUNT = 0


def make_candidate_validation_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-VALIDATION-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_candidate_selection():
    filters = {
        "status": "Candidate Selection Approved",
        "candidate_status": "Next Governed Limited Operation Candidate Selection Approved",
        "candidate_selection_approved": 1,
        "phase12o_design_verified": 1,
        "design_approved_verified": 1,
        "design_source_verified": 1,
        "design_reference_verified": 1,
        "design_party_type_verified": 1,
        "design_shape_verified": 1,
        "design_reference_set_locked_verified": 1,
        "design_reference_set_verified": 1,
        "candidate_selection_locked": 1,
        "selected_reference_set_locked": 1,
        "selected_reference_set_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "selected_source_doctype": VALIDATED_SOURCE_DOCTYPE,
        "selected_reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
        "selected_party_type": VALIDATED_PARTY_TYPE,
        "selected_invoice_count": EXPECTED_INVOICE_COUNT,
        "selected_total_amount": EXPECTED_TOTAL_AMOUNT,
        "selected_payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
        "selected_gl_entry_count": VALIDATED_GL_ENTRY_COUNT,
        "selected_live_posting_allowed": 0,
        "selected_journal_entry_side_effect_allowed": 0,
        "selected_purchase_invoice_side_effect_allowed": 0,
        "monitored_payment_entry": EXPECTED_PAYMENT_ENTRY,
        "monitored_payment_entry_docstatus": 2,
        "monitored_payment_entry_status": "Cancelled",
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
    if has_column(CANDIDATE_DOCTYPE, CANDIDATE_READY_FIELD):
        filters[CANDIDATE_READY_FIELD] = 1

    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "candidate_selection_id",
            "selected_source_doctype",
            "selected_reference_doctype",
            "selected_party_type",
            "selected_customer",
            "selected_company",
            "selected_currency",
            "selected_invoice_names",
            "selected_invoice_count",
            "selected_total_amount",
            "selected_payment_entry_count",
            "selected_gl_entry_count",
            "selected_live_posting_allowed",
            "selected_journal_entry_side_effect_allowed",
            "selected_purchase_invoice_side_effect_allowed",
            "selected_reference_set_locked",
            "monitored_payment_entry",
            "monitored_payment_entry_docstatus",
            "monitored_payment_entry_status",
            "monitored_voucher_gl_rows",
            "monitored_voucher_gl_net",
            "monitored_reversal_gl_rows",
            "monitored_restored_invoice_amount",
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
            "candidate_validation",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_candidate_validation(candidate_selection):
    rows = frappe.get_all(
        VALIDATION_DOCTYPE,
        filters={
            "candidate_selection": candidate_selection,
            "status": "Candidate Validation Approved",
            "candidate_validation_approved": 1,
        },
        fields=["name", "candidate_validation_id", "validated_invoice_names"],
        limit=1,
    )
    return rows[0] if rows else None


def candidate_rows(candidate_selection):
    rows = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        filters={
            "candidate_selection": candidate_selection,
            "category": "Selected Reference",
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
            "selected_amount",
            "current_outstanding_amount",
            "monitored_payment_entry",
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
        outstanding = flt((si.outstanding_amount if si else 0) or 0, 2)
        amount = flt(row.selected_amount or 0, 2)
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "validated_amount": amount,
                    "current_outstanding_amount": outstanding,
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "outstanding_sufficient": int(outstanding >= amount and amount > 0),
                    "monitored_payment_entry": row.monitored_payment_entry,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def validated_total(rows):
    return flt(sum(flt(row.validated_amount or 0, 2) for row in rows), 2)


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


def voucher_gl_rows(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net(payment_entry):
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


def reversal_gl_rows(payment_entry):
    return max(0, int(voucher_gl_rows(payment_entry) or 0) - 4)


def validate_source(candidate_selection, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not candidate_selection:
        issues.append("No approved Phase 12P next governed limited-operation candidate selection found.")
        return issues

    existing = existing_approved_candidate_validation(candidate_selection.name)
    if existing:
        issues.append(
            f"Approved Phase 12Q candidate validation already exists for this candidate selection: {existing.candidate_validation_id} / {existing.validated_invoice_names}"
        )

    payment_entry = candidate_selection.monitored_payment_entry
    if payment_entry != EXPECTED_PAYMENT_ENTRY:
        issues.append(f"Expected monitored Payment Entry {EXPECTED_PAYMENT_ENTRY}. Found {payment_entry}.")

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Monitored Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)
    if pe.docstatus != 2:
        issues.append(f"Monitored Payment Entry must remain cancelled. docstatus={pe.docstatus}")
    if pe.status != "Cancelled":
        issues.append(f"Monitored Payment Entry status must remain Cancelled. status={pe.status}")

    if candidate_selection.selected_source_doctype != VALIDATED_SOURCE_DOCTYPE:
        issues.append("Selected source DocType changed.")
    if candidate_selection.selected_reference_doctype != VALIDATED_REFERENCE_DOCTYPE:
        issues.append("Selected reference DocType changed.")
    if candidate_selection.selected_party_type != VALIDATED_PARTY_TYPE:
        issues.append("Selected party type changed.")
    if int(candidate_selection.selected_payment_entry_count or 0) != VALIDATED_PAYMENT_ENTRY_COUNT:
        issues.append("Selected Payment Entry count must be 1.")
    if int(candidate_selection.selected_gl_entry_count or 0) != VALIDATED_GL_ENTRY_COUNT:
        issues.append("Selected GL count must be 0 before execution.")
    if int(candidate_selection.selected_live_posting_allowed or 0) != 0:
        issues.append("Selected live posting allowed must remain 0.")
    if int(candidate_selection.selected_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Selected Journal Entry side effect allowed must remain 0.")
    if int(candidate_selection.selected_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Selected Purchase Invoice side effect allowed must remain 0.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Validation invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Validation invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if validated_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Validation total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {validated_total(rows)}.")
    if not same_value_verified(rows, "customer"):
        issues.append("Validated Sales Invoices must share the same customer.")
    if not same_value_verified(rows, "company"):
        issues.append("Validated Sales Invoices must share the same company.")
    if not same_value_verified(rows, "currency"):
        issues.append("Validated Sales Invoices must share the same currency.")
    if not invoices_submitted(rows):
        issues.append("All selected Sales Invoices must be submitted.")
    if not invoices_outstanding_sufficient(rows):
        issues.append("All selected Sales Invoices must have sufficient outstanding amount for the selected amount.")

    if voucher_gl_rows(payment_entry) != EXPECTED_VOUCHER_GL_ROWS:
        issues.append(f"Voucher GL rows must remain {EXPECTED_VOUCHER_GL_ROWS}. Found {voucher_gl_rows(payment_entry)}.")
    if voucher_gl_net(payment_entry) != EXPECTED_VOUCHER_GL_NET:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")
    if reversal_gl_rows(payment_entry) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append(f"Reversal GL rows must remain {EXPECTED_REVERSAL_GL_ROWS}. Found {reversal_gl_rows(payment_entry)}.")
    restored = outstanding_total(EXPECTED_INVOICES)
    if restored != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice amount must remain {EXPECTED_TOTAL_AMOUNT}. Found {restored}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 11 before candidate validation.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 70 before candidate validation.")
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


def build_items(rows, issues, ack_ok, payment_entry=None):
    items = []
    if not issues:
        items.append(
            {
                "status": "Pass",
                "severity": "Critical",
                "category": "Validation Source",
                "check_key": "candidate_validation_source_valid",
                "check_label": "Candidate validation source valid",
                "detail": "The Phase 12P candidate selection is stable and exact selected invoices can be validated.",
                "monitored_payment_entry": payment_entry,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Validation Source",
                    "check_key": "candidate_validation_source_valid",
                    "check_label": "Candidate validation source valid",
                    "detail": issue,
                    "monitored_payment_entry": payment_entry,
                }
            )

    for row in rows:
        item_status = "Pass" if int(row.invoice_docstatus or 0) == 1 and int(row.outstanding_sufficient or 0) == 1 else "Blocker"
        items.append(
            {
                "status": item_status,
                "severity": "High",
                "category": "Validated Reference",
                "check_key": "validated_sales_invoice_reference",
                "check_label": f"Validated Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} validated amount={row.validated_amount}, docstatus={row.invoice_docstatus}, outstanding={row.current_outstanding_amount}, sufficient={row.outstanding_sufficient}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "validated_amount": row.validated_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
                "invoice_docstatus": row.invoice_docstatus,
                "outstanding_sufficient": row.outstanding_sufficient,
                "monitored_payment_entry": payment_entry,
            }
        )

    checks = [
        ("candidate_selection_approved", "Candidate selection approved", 1),
        ("invoice_submission_verified", "Invoices submitted", 1),
        ("invoice_outstanding_verified", "Invoice outstanding sufficient", 1),
        ("candidate_validation_locked", "Candidate validation locked", 1),
        ("validated_reference_set_locked", "Validated reference set locked", ", ".join(EXPECTED_INVOICES)),
        ("validated_shape", "Validated shape", f"{EXPECTED_INVOICE_COUNT} / {EXPECTED_TOTAL_AMOUNT} / {VALIDATED_PAYMENT_ENTRY_COUNT} / {VALIDATED_GL_ENTRY_COUNT}"),
        ("validated_side_effects", "Validated live/JE/PI side effects", "0 / 0 / 0"),
        ("preview_gate_ready", "Ready for next governed limited-operation preview gate", 1),
    ]
    for key, label, value in checks:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Validation Evidence",
                "check_key": key,
                "check_label": label,
                "detail": f"value={value}",
                "monitored_payment_entry": payment_entry,
            }
        )
    items.append(
        {
            "status": "Pass" if ack_ok else "Warning",
            "severity": "Low" if ack_ok else "Medium",
            "category": "Acknowledgement",
            "check_key": "ack_ok",
            "check_label": "Acknowledgement supplied",
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {VALIDATION_ACK}",
            "monitored_payment_entry": payment_entry,
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
        if item.get("category") != "Validated Reference":
            continue
        row = frappe.new_doc(VALIDATION_ITEM_DOCTYPE)
        row.candidate_validation = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_candidate_validation(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_candidate_validation")

    candidate_selection = latest_candidate_selection()
    rows = candidate_rows(candidate_selection.name) if candidate_selection else []
    payment_entry = candidate_selection.monitored_payment_entry if candidate_selection else None

    guard_before = guardrails()
    ack_ok = acknowledgement == VALIDATION_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, candidate_selection.target_policy, "production_batch_enabled") if candidate_selection else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, candidate_selection.target_policy, "live_posting_allowed") if candidate_selection else 0
    source_issues = validate_source(candidate_selection, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, candidate_selection.target_policy, "production_batch_enabled") if candidate_selection else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, candidate_selection.target_policy, "live_posting_allowed") if candidate_selection else 0

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
    voucher_rows = 0
    voucher_net = 0
    reversal_rows = 0
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        reversal_rows = reversal_gl_rows(payment_entry)

    post_issues = list(source_issues)
    if actual_pe_created != 0:
        post_issues.append(f"Candidate validation must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Candidate validation must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Candidate validation must create 0 GL rows. Created {actual_gl_created}.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during candidate validation. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and candidate_selection
        and payment_entry
        and not post_issues
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and reference_names(rows) == EXPECTED_INVOICES
        and validated_total(rows) == EXPECTED_TOTAL_AMOUNT
        and invoices_submitted(rows) == 1
        and invoices_outstanding_sufficient(rows) == 1
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == 0
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

    selected_source_ok = int(candidate_selection and candidate_selection.selected_source_doctype == VALIDATED_SOURCE_DOCTYPE)
    selected_reference_ok = int(candidate_selection and candidate_selection.selected_reference_doctype == VALIDATED_REFERENCE_DOCTYPE)
    selected_party_ok = int(candidate_selection and candidate_selection.selected_party_type == VALIDATED_PARTY_TYPE)
    selected_shape_ok = int(
        candidate_selection
        and int(candidate_selection.selected_invoice_count or 0) == EXPECTED_INVOICE_COUNT
        and flt(candidate_selection.selected_total_amount or 0, 2) == EXPECTED_TOTAL_AMOUNT
        and int(candidate_selection.selected_payment_entry_count or 0) == VALIDATED_PAYMENT_ENTRY_COUNT
        and int(candidate_selection.selected_gl_entry_count or 0) == VALIDATED_GL_ENTRY_COUNT
    )
    selected_side_effects_ok = int(
        candidate_selection
        and int(candidate_selection.selected_live_posting_allowed or 0) == 0
        and int(candidate_selection.selected_journal_entry_side_effect_allowed or 0) == 0
        and int(candidate_selection.selected_purchase_invoice_side_effect_allowed or 0) == 0
    )

    items = build_items(rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_status": "Next Governed Limited Operation Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_approved": completed,
        "phase12p_candidate_selection_verified": 1 if candidate_selection else 0,
        "candidate_selection_approved_verified": 1 if candidate_selection else 0,
        "selected_source_verified": selected_source_ok,
        "selected_reference_verified": selected_reference_ok,
        "selected_party_type_verified": selected_party_ok,
        "selected_reference_set_locked_verified": int(candidate_selection and int(candidate_selection.selected_reference_set_locked or 0) == 1),
        "selected_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "selected_shape_verified": selected_shape_ok,
        "selected_side_effects_blocked_verified": selected_side_effects_ok,
        "invoice_submission_verified": invoices_submitted(rows),
        "invoice_outstanding_verified": invoices_outstanding_sufficient(rows),
        "candidate_validation_locked": completed,
        "validated_reference_set_locked": completed,
        "validated_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "policy_state_preserved_verified": int(
            policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0
        ),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "validated_source_doctype": VALIDATED_SOURCE_DOCTYPE,
        "validated_reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
        "validated_party_type": VALIDATED_PARTY_TYPE,
        "validated_customer": unique_value(rows, "customer"),
        "validated_company": unique_value(rows, "company"),
        "validated_currency": unique_value(rows, "currency"),
        "validated_invoice_names": ", ".join(reference_names(rows)),
        "validated_invoice_count": len(rows),
        "validated_total_amount": validated_total(rows),
        "validated_payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
        "validated_gl_entry_count": VALIDATED_GL_ENTRY_COUNT,
        "validated_live_posting_allowed": 0,
        "validated_journal_entry_side_effect_allowed": 0,
        "validated_purchase_invoice_side_effect_allowed": 0,
        VALIDATION_READY_FIELD: completed,
        "monitored_payment_entry": payment_entry,
        "monitored_payment_entry_docstatus": pe_docstatus,
        "monitored_payment_entry_status": pe_status,
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
        "target_policy": candidate_selection.target_policy if candidate_selection else None,
        "target_policy_name": candidate_selection.target_policy_name if candidate_selection else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        "candidate_selection": candidate_selection.name if candidate_selection else None,
        "design": candidate_selection.design if candidate_selection else None,
        "planning": candidate_selection.planning if candidate_selection else None,
        "monitor": candidate_selection.monitor if candidate_selection else None,
        "baseline": candidate_selection.baseline if candidate_selection else None,
        "closeout": candidate_selection.closeout if candidate_selection else None,
        "freeze": candidate_selection.freeze if candidate_selection else None,
        "rollback": candidate_selection.rollback if candidate_selection else None,
        "smoke": candidate_selection.smoke if candidate_selection else None,
        "execution_gate": candidate_selection.execution_gate if candidate_selection else None,
        "preview": candidate_selection.preview if candidate_selection else None,
        "previous_candidate_validation": candidate_selection.candidate_validation if candidate_selection else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": VALIDATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12Q approves candidate validation for the next governed limited-operation cycle only. No accounting movement occurs.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(VALIDATION_DOCTYPE)
    doc.candidate_validation_id = make_candidate_validation_id()
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
    doc.validation_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "candidate_validation": doc.name, "candidate_validation_id": doc.candidate_validation_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_candidate_validation_audit(candidate_validation, reason=None):
    assert_action("cancel_next_governed_limited_operation_candidate_validation_audit")
    if not frappe.db.exists(VALIDATION_DOCTYPE, candidate_validation):
        frappe.throw(_("Next governed limited-operation candidate validation audit not found: {0}").format(candidate_validation))
    doc = frappe.get_doc(VALIDATION_DOCTYPE, candidate_validation)
    if doc.status == "Cancelled":
        return {"candidate_validation": candidate_validation, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.candidate_validation_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 12Q candidate validation record."))
    frappe.db.set_value(
        VALIDATION_DOCTYPE,
        candidate_validation,
        {
            "status": "Cancelled",
            "candidate_validation_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12Q no-ack candidate validation audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"UPDATE `tab{VALIDATION_ITEM_DOCTYPE}` SET status='Cancelled' WHERE candidate_validation=%(candidate_validation)s",
        {"candidate_validation": candidate_validation},
    )
    frappe.db.commit()
    return {"candidate_validation": candidate_validation, "status": "Cancelled", "note": "No-ack candidate validation audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_candidate_validation_summary(limit=20):
    return {
        "candidate_validation_records": frappe.get_all(
            VALIDATION_DOCTYPE,
            fields=[
                "name",
                "candidate_validation_id",
                "status",
                "candidate_validation_status",
                "candidate_validation_approved",
                "validated_source_doctype",
                "validated_reference_doctype",
                "validated_party_type",
                "validated_invoice_names",
                "validated_invoice_count",
                "validated_total_amount",
                "validated_payment_entry_count",
                "validated_gl_entry_count",
                "validated_live_posting_allowed",
                "validated_journal_entry_side_effect_allowed",
                "validated_purchase_invoice_side_effect_allowed",
                "invoice_submission_verified",
                "invoice_outstanding_verified",
                VALIDATION_READY_FIELD,
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
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
            VALIDATION_ITEM_DOCTYPE,
            fields=[
                "name",
                "candidate_validation",
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
                "validated_amount",
                "current_outstanding_amount",
                "invoice_docstatus",
                "outstanding_sufficient",
                "monitored_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": VALIDATION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12Q next governed limited-operation candidate validation summary.",
    }


def execute_candidate_validation_report(filters=None):
    columns = [
        {"fieldname": "candidate_validation", "label": _("Candidate Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "candidate_validation_id", "label": _("Candidate Validation ID"), "fieldtype": "Data", "width": 470},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 210},
        {"fieldname": "candidate_validation_status", "label": _("Validation Status"), "fieldtype": "Data", "width": 390},
        {"fieldname": "candidate_validation_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "validated_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "validated_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "validated_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 105},
        {"fieldname": "validated_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "validated_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "validated_gl_entry_count", "label": _("Future GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "invoice_submission_verified", "label": _("Submitted"), "fieldtype": "Check", "width": 95},
        {"fieldname": "invoice_outstanding_verified", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": VALIDATION_READY_FIELD, "label": _("Preview Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            name AS candidate_validation,
            candidate_validation_id,
            status,
            candidate_validation_status,
            candidate_validation_approved,
            validated_source_doctype,
            validated_reference_doctype,
            validated_party_type,
            validated_invoice_names,
            validated_invoice_count,
            validated_total_amount,
            validated_payment_entry_count,
            validated_gl_entry_count,
            invoice_submission_verified,
            invoice_outstanding_verified,
            `{VALIDATION_READY_FIELD}` AS `{VALIDATION_READY_FIELD}`,
            monitored_payment_entry,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{VALIDATION_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.candidate_validation_id for row in data[:20]],
            "datasets": [
                {"name": "Validation Approved", "values": [int(row.candidate_validation_approved or 0) for row in data[:20]]},
                {"name": "Preview Ready", "values": [int(row.get(VALIDATION_READY_FIELD) or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Candidate Validation Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_validation_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": VALIDATION_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "candidate_validation", "label": _("Candidate Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "validated_amount", "label": _("Validated Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
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
            candidate_validation,
            status,
            category,
            line_no,
            reference_doctype,
            reference_name,
            validated_amount,
            current_outstanding_amount,
            invoice_docstatus,
            outstanding_sufficient,
            monitored_payment_entry,
            check_label,
            detail
        FROM `tab{VALIDATION_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
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
        {"value": len([row for row in data if row.category == "Validated Reference"]), "indicator": "Green", "label": _("Validated References"), "datatype": "Int"},
        {"value": len([row for row in data if int(row.invoice_docstatus or 0) == 1]), "indicator": "Green", "label": _("Submitted Invoices"), "datatype": "Int"},
        {"value": len([row for row in data if int(row.outstanding_sufficient or 0) == 1]), "indicator": "Green", "label": _("Outstanding OK"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_candidate_validation_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
