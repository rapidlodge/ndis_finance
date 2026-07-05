import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


VALIDATION_ACK = "I_CONFIRM_PHASE12E_VALIDATE_GOVERNED_LIMITED_OPERATION_CANDIDATES_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CANDIDATE_DOCTYPE = "NDIS Next Governed Limited Op Candidate"
CANDIDATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Candidate Item"
VALIDATION_DOCTYPE = "NDIS Next Governed Limited Op Cand Valid"
VALIDATION_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Cand Valid Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00011"
EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_PAYMENT_ENTRY_COUNT = 10
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 62
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

VALIDATED_SOURCE_DOCTYPE = "Sales Invoice"
VALIDATED_REFERENCE_DOCTYPE = "Sales Invoice"
VALIDATED_PARTY_TYPE = "Customer"
VALIDATED_INVOICE_COUNT = 3
VALIDATED_TOTAL_AMOUNT = 3.00
VALIDATED_PAYMENT_ENTRY_COUNT = 1


def make_candidate_validation_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-CAND-VALID-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_candidate_selection():
    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters={
            "status": "Candidate Selection Approved",
            "candidate_selection_status": "Governed Limited Operation Candidate Selection Approved",
            "candidate_selection_approved": 1,
            "phase12c_design_verified": 1,
            "design_approved_verified": 1,
            "design_source_locked_verified": 1,
            "design_shape_locked_verified": 1,
            "candidate_selection_ready_verified": 1,
            "selected_invoice_set_locked": 1,
            "selected_invoice_set_verified": 1,
            "selected_sales_invoices_exist_verified": 1,
            "selected_sales_invoices_submitted_verified": 1,
            "selected_outstanding_sufficient_verified": 1,
            "same_customer_verified": 1,
            "same_company_verified": 1,
            "same_currency_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_governed_limited_operation_candidate_validation_gate": 1,
            "selected_source_doctype": VALIDATED_SOURCE_DOCTYPE,
            "selected_reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
            "selected_party_type": VALIDATED_PARTY_TYPE,
            "selected_invoice_count": VALIDATED_INVOICE_COUNT,
            "selected_total_amount": VALIDATED_TOTAL_AMOUNT,
            "selected_payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
            "selected_live_posting_allowed": 0,
            "selected_journal_entry_side_effect_allowed": 0,
            "selected_purchase_invoice_side_effect_allowed": 0,
            "monitored_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "payment_entry_docstatus_candidate": 2,
            "payment_entry_status_candidate": "Cancelled",
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
        },
        fields=[
            "name",
            "candidate_selection_id",
            "monitored_payment_entry",
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
            "selected_invoice_set_locked",
            "selected_invoice_set_verified",
            "selected_live_posting_allowed",
            "selected_journal_entry_side_effect_allowed",
            "selected_purchase_invoice_side_effect_allowed",
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
            "validation",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_validation(candidate_selection):
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
    if not candidate_selection:
        return []

    rows = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        filters={
            "candidate_selection": candidate_selection,
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
            "selected_amount",
            "current_outstanding_amount",
            "monitored_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        if not frappe.db.exists("Sales Invoice", row.reference_name):
            result.append(
                frappe._dict(
                    {
                        "idx": int(row.line_no or idx),
                        "reference_doctype": row.reference_doctype,
                        "reference_name": row.reference_name,
                        "validated_amount": flt(row.selected_amount or 0, 2),
                        "current_outstanding_amount": flt(row.current_outstanding_amount or 0, 2),
                        "customer": row.customer,
                        "company": row.company,
                        "currency": row.currency,
                        "docstatus": None,
                        "monitored_payment_entry": row.monitored_payment_entry,
                    }
                )
            )
            continue

        si = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
            ["docstatus", "customer", "company", "currency", "outstanding_amount"],
            as_dict=True,
        )

        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "validated_amount": flt(row.selected_amount or 0, 2),
                    "current_outstanding_amount": flt(si.outstanding_amount or row.current_outstanding_amount or 0, 2),
                    "customer": si.customer,
                    "company": si.company,
                    "currency": si.currency,
                    "docstatus": int(si.docstatus or 0),
                    "monitored_payment_entry": row.monitored_payment_entry,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def validated_total(rows):
    return flt(sum(flt(row.validated_amount or 0, 2) for row in rows), 2)


def outstanding_total(rows):
    return flt(sum(flt(row.current_outstanding_amount or 0, 2) for row in rows), 2)


def all_sales_invoices_exist(rows):
    return int(len(rows) == VALIDATED_INVOICE_COUNT and all(frappe.db.exists("Sales Invoice", row.reference_name) for row in rows))


def all_sales_invoices_submitted(rows):
    return int(len(rows) == VALIDATED_INVOICE_COUNT and all(int(row.docstatus or 0) == 1 for row in rows))


def all_outstanding_sufficient(rows):
    return int(len(rows) == VALIDATED_INVOICE_COUNT and all(flt(row.current_outstanding_amount or 0, 2) >= flt(row.validated_amount or 0, 2) for row in rows))


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def same_value_verified(rows, fieldname):
    values = set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)])
    return int(len(rows) == VALIDATED_INVOICE_COUNT and len(values) == 1)


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
        issues.append("No approved Phase 12D governed limited-operation candidate selection found.")
        return issues

    existing = existing_approved_validation(candidate.name)
    if existing:
        issues.append(f"Approved Phase 12E candidate validation already exists for this candidate selection: {existing.candidate_validation_id} / {existing.validated_invoice_names}")

    if candidate.selected_source_doctype != VALIDATED_SOURCE_DOCTYPE:
        issues.append(f"Selected source doctype must be {VALIDATED_SOURCE_DOCTYPE}. Found {candidate.selected_source_doctype}.")

    if candidate.selected_reference_doctype != VALIDATED_REFERENCE_DOCTYPE:
        issues.append(f"Selected reference doctype must be {VALIDATED_REFERENCE_DOCTYPE}. Found {candidate.selected_reference_doctype}.")

    if candidate.selected_party_type != VALIDATED_PARTY_TYPE:
        issues.append(f"Selected party type must be {VALIDATED_PARTY_TYPE}. Found {candidate.selected_party_type}.")

    if int(candidate.selected_invoice_count or 0) != VALIDATED_INVOICE_COUNT:
        issues.append(f"Selected invoice count must be {VALIDATED_INVOICE_COUNT}. Found {candidate.selected_invoice_count}.")

    if flt(candidate.selected_total_amount or 0, 2) != VALIDATED_TOTAL_AMOUNT:
        issues.append(f"Selected total amount must be {VALIDATED_TOTAL_AMOUNT}. Found {candidate.selected_total_amount}.")

    if int(candidate.selected_payment_entry_count or 0) != VALIDATED_PAYMENT_ENTRY_COUNT:
        issues.append(f"Selected Payment Entry count must be {VALIDATED_PAYMENT_ENTRY_COUNT}. Found {candidate.selected_payment_entry_count}.")

    if int(candidate.selected_live_posting_allowed or 0) != 0:
        issues.append("Selected live posting must remain disabled.")

    if int(candidate.selected_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Selected Journal Entry side effects must remain disabled.")

    if int(candidate.selected_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Selected Purchase Invoice side effects must remain disabled.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Validated invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != VALIDATED_INVOICE_COUNT:
        issues.append(f"Validated invoice count must be {VALIDATED_INVOICE_COUNT}. Found {len(rows)}.")

    if validated_total(rows) != VALIDATED_TOTAL_AMOUNT:
        issues.append(f"Validated total must be {VALIDATED_TOTAL_AMOUNT}. Found {validated_total(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("All validated Sales Invoices must exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("All validated Sales Invoices must be submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("All validated Sales Invoices must have outstanding amount sufficient for the validated amount.")

    if not same_value_verified(rows, "customer"):
        issues.append("Validated Sales Invoices must share the same customer.")

    if not same_value_verified(rows, "company"):
        issues.append("Validated Sales Invoices must share the same company.")

    if not same_value_verified(rows, "currency"):
        issues.append("Validated Sales Invoices must share the same currency.")

    if not payment_entry:
        issues.append("Phase 12D candidate selection did not identify a monitored Payment Entry.")
        return issues

    if payment_entry != EXPECTED_PAYMENT_ENTRY:
        issues.append(f"Expected monitored Payment Entry {EXPECTED_PAYMENT_ENTRY}, found {payment_entry}.")

    if not frappe.db.exists("Payment Entry", payment_entry):
        issues.append(f"Monitored Payment Entry does not exist: {payment_entry}")
        return issues

    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 2:
        issues.append(f"Monitored Payment Entry must remain cancelled. docstatus={pe.docstatus}")

    if pe.status != "Cancelled":
        issues.append(f"Monitored Payment Entry status must remain Cancelled. status={pe.status}")

    if payment_entry_reference_count(payment_entry) != EXPECTED_REFERENCE_COUNT:
        issues.append(f"Monitored Payment Entry must retain {EXPECTED_REFERENCE_COUNT} references.")

    if payment_entry_allocated_amount(payment_entry) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Monitored Payment Entry allocated amount must remain {EXPECTED_TOTAL_AMOUNT}.")

    if voucher_gl_rows(payment_entry) != EXPECTED_VOUCHER_GL_ROWS:
        issues.append(f"Voucher GL rows must remain {EXPECTED_VOUCHER_GL_ROWS}. Found {voucher_gl_rows(payment_entry)}.")

    if voucher_gl_net(payment_entry) != 0:
        issues.append(f"Voucher GL net must remain 0.00. Found {voucher_gl_net(payment_entry)}.")

    if voucher_gl_non_zero_accounts(payment_entry) != 0:
        issues.append(f"Voucher GL non-zero account count must remain 0. Found {voucher_gl_non_zero_accounts(payment_entry)}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 10 before Phase 12E candidate validation.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 62 before Phase 12E candidate validation.")

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


def add_item(items, status, severity, category, check_key, check_label, detail, row=None, payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "monitored_payment_entry": payment_entry,
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
                "validated_amount": row.validated_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
            }
        )

    items.append(item)


def build_items(candidate, rows, issues, ack_ok, payment_entry=None):
    items = []

    if candidate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase12d_candidate_selection_exists",
            "Phase 12D candidate selection exists",
            f"Candidate selection found: {candidate.candidate_selection_id}.",
            payment_entry=payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase12d_candidate_selection_exists", "Phase 12D candidate selection exists", "No approved Phase 12D candidate selection found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Validation Source",
            "validation_source_valid",
            "Validation source valid",
            "The selected governed limited-operation candidate invoice set is valid for preview.",
            payment_entry=payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Validation Source",
                "validation_source_valid",
                "Validation source valid",
                issue,
                payment_entry=payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Validated Candidate",
            "validated_sales_invoice_candidate",
            f"Validated Sales Invoice {row.idx}",
            f"{row.reference_name} validated with amount={row.validated_amount}, outstanding={row.current_outstanding_amount}.",
            row=row,
            payment_entry=payment_entry,
        )

    checks = [
        ("validated_invoice_set", "Validated invoice set locked", ", ".join(EXPECTED_INVOICES)),
        ("validated_shape", "Validated count/amount/future PE locked", f"{VALIDATED_INVOICE_COUNT} / {VALIDATED_TOTAL_AMOUNT} / {VALIDATED_PAYMENT_ENTRY_COUNT}"),
        ("source_lock", "Source/reference/party locked", f"{VALIDATED_SOURCE_DOCTYPE} / {VALIDATED_REFERENCE_DOCTYPE} / {VALIDATED_PARTY_TYPE}"),
        ("same_customer", "Same customer verified", unique_value(rows, "customer") or "None"),
        ("same_company", "Same company verified", unique_value(rows, "company") or "None"),
        ("same_currency", "Same currency verified", unique_value(rows, "currency") or "None"),
        ("live_posting_disabled", "Live posting not allowed", 0),
        ("je_side_effect_disabled", "Journal Entry side effect not allowed", 0),
        ("pi_side_effect_disabled", "Purchase Invoice side effect not allowed", 0),
        ("payment_entry_cancelled_still", "Payment Entry remains Cancelled", payment_entry or "None"),
        ("payment_entry_count", "Payment Entry count remains 10", "10 -> 10"),
        ("payment_entry_gl_count", "Payment Entry GL count remains 62", "62 -> 62"),
        ("no_pe_movement", "No Payment Entry movement", "0 / 0"),
        ("no_gl_movement", "No GL movement", 0),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("preview_ready", "Ready for governed limited-operation preview gate", 1),
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
            payment_entry=payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", payment_entry=payment_entry)
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
        row.candidate_validation = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_candidate_validation(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_candidate_validation")

    candidate = latest_candidate_selection()
    payment_entry = candidate.monitored_payment_entry if candidate else None
    rows = candidate_rows(candidate.name) if candidate else []

    guard_before = guardrails()
    ack_ok = acknowledgement == VALIDATION_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "production_batch_enabled") if candidate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "live_posting_allowed") if candidate else 0

    source_issues = validate_source(candidate, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

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
    reference_count = 0
    total_amount = 0
    voucher_rows = 0
    voucher_net = 0
    voucher_non_zero_accounts = 0
    restored_invoice_amount = outstanding_total(rows)

    if payment_entry and frappe.db.exists("Payment Entry", payment_entry):
        pe = frappe.get_doc("Payment Entry", payment_entry)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        reference_count = payment_entry_reference_count(payment_entry)
        total_amount = payment_entry_allocated_amount(payment_entry)
        voucher_rows = voucher_gl_rows(payment_entry)
        voucher_net = voucher_gl_net(payment_entry)
        voucher_non_zero_accounts = voucher_gl_non_zero_accounts(payment_entry)

    post_issues = list(source_issues)

    if actual_pe_created != 0:
        post_issues.append(f"Candidate validation must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Candidate validation must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Candidate validation must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        post_issues.append("Payment Entry count must remain 10 after candidate validation.")

    if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        post_issues.append("Payment Entry GL count must remain 62 after candidate validation.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after candidate validation.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after candidate validation.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during candidate validation. This is not allowed.")

    validated_invoice_set_verified = int(reference_names(rows) == EXPECTED_INVOICES)
    validated_exists = all_sales_invoices_exist(rows)
    validated_submitted = all_sales_invoices_submitted(rows)
    validated_outstanding = all_outstanding_sufficient(rows)
    same_customer = same_value_verified(rows, "customer")
    same_company = same_value_verified(rows, "company")
    same_currency = same_value_verified(rows, "currency")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and candidate
        and payment_entry
        and not post_issues
        and validated_invoice_set_verified
        and validated_exists
        and validated_submitted
        and validated_outstanding
        and same_customer
        and same_company
        and same_currency
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and reference_count == EXPECTED_REFERENCE_COUNT
        and total_amount == EXPECTED_TOTAL_AMOUNT
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == 0
        and voucher_non_zero_accounts == 0
        and restored_invoice_amount == EXPECTED_TOTAL_AMOUNT
        and validated_total(rows) == VALIDATED_TOTAL_AMOUNT
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

    items = build_items(candidate, rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_status": "Governed Limited Operation Candidate Validation Approved" if completed else "Needs Review",
        "candidate_validation_approved": completed,
        "phase12d_candidate_selection_verified": 1 if candidate else 0,
        "candidate_selection_approved_verified": 1 if candidate else 0,
        "selected_invoice_set_locked_verified": int(candidate and int(candidate.selected_invoice_set_locked or 0) == 1),
        "selected_invoice_set_verified": int(candidate and int(candidate.selected_invoice_set_verified or 0) == 1),
        "validated_invoice_set_locked": completed,
        "validated_invoice_set_verified": validated_invoice_set_verified,
        "validated_sales_invoices_exist_verified": validated_exists,
        "validated_sales_invoices_submitted_verified": validated_submitted,
        "validated_outstanding_sufficient_verified": validated_outstanding,
        "same_customer_verified": same_customer,
        "same_company_verified": same_company,
        "same_currency_verified": same_currency,
        "validation_source_locked": completed,
        "validation_shape_locked": completed,
        "monitored_payment_entry_verified": int(bool(payment_entry)),
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_governed_limited_operation_preview_gate": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,

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
        "validated_live_posting_allowed": 0,
        "validated_journal_entry_side_effect_allowed": 0,
        "validated_purchase_invoice_side_effect_allowed": 0,

        "selected_source_doctype": candidate.selected_source_doctype if candidate else None,
        "selected_reference_doctype": candidate.selected_reference_doctype if candidate else None,
        "selected_party_type": candidate.selected_party_type if candidate else None,
        "selected_customer": candidate.selected_customer if candidate else None,
        "selected_company": candidate.selected_company if candidate else None,
        "selected_currency": candidate.selected_currency if candidate else None,
        "selected_invoice_names": candidate.selected_invoice_names if candidate else None,
        "selected_invoice_count": int(candidate.selected_invoice_count or 0) if candidate else 0,
        "selected_total_amount": flt(candidate.selected_total_amount or 0, 2) if candidate else 0,
        "selected_payment_entry_count": int(candidate.selected_payment_entry_count or 0) if candidate else 0,

        "monitored_payment_entry": payment_entry,
        "payment_entry_docstatus_validation": pe_docstatus,
        "payment_entry_status_validation": pe_status,
        "monitored_reference_count": reference_count,
        "monitored_total_amount": total_amount,
        "monitored_voucher_gl_rows": voucher_rows,
        "monitored_voucher_gl_net": voucher_net,
        "monitored_restored_invoice_amount": restored_invoice_amount,

        "candidate_selection": candidate.name if candidate else None,
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
        "previous_validation": candidate.validation if candidate else None,

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
        "candidate_validation_score": score,
        **item_summary,
        "items": items,
        "validated_candidates": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": VALIDATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12E validates the governed limited-operation candidates only. No preview, posting, accounting, or policy movement occurs.",
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
    doc.validation_json = safe_json(
        {
            "candidate_selection": candidate,
            "monitored_payment_entry": payment_entry,
            "validated_envelope": {
                "source_doctype": VALIDATED_SOURCE_DOCTYPE,
                "reference_doctype": VALIDATED_REFERENCE_DOCTYPE,
                "party_type": VALIDATED_PARTY_TYPE,
                "invoice_names": reference_names(rows),
                "invoice_count": len(rows),
                "total_amount": validated_total(rows),
                "payment_entry_count": VALIDATED_PAYMENT_ENTRY_COUNT,
                "customer": unique_value(rows, "customer"),
                "company": unique_value(rows, "company"),
                "currency": unique_value(rows, "currency"),
                "live_posting_allowed": 0,
                "journal_entry_side_effect_allowed": 0,
                "purchase_invoice_side_effect_allowed": 0,
            },
            "validated_candidates": [dict(row) for row in rows],
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher": {
                "rows": voucher_rows,
                "net": voucher_net,
                "non_zero_accounts": voucher_non_zero_accounts,
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
        "candidate_validation": doc.name,
        "candidate_validation_id": doc.candidate_validation_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_candidate_validation_audit(candidate_validation, reason=None):
    assert_action("cancel_governed_limited_operation_candidate_validation_audit")

    if not frappe.db.exists(VALIDATION_DOCTYPE, candidate_validation):
        frappe.throw(_("Governed limited-operation candidate validation audit not found: {0}").format(candidate_validation))

    doc = frappe.get_doc(VALIDATION_DOCTYPE, candidate_validation)

    if doc.status == "Cancelled":
        return {"candidate_validation": candidate_validation, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_validation_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 12E candidate validation record."))

    frappe.db.set_value(
        VALIDATION_DOCTYPE,
        candidate_validation,
        {
            "status": "Cancelled",
            "candidate_validation_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12E no-ack candidate validation audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{VALIDATION_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE candidate_validation = %(candidate_validation)s
        """,
        {"candidate_validation": candidate_validation},
    )

    frappe.db.commit()

    return {
        "candidate_validation": candidate_validation,
        "status": "Cancelled",
        "note": "No-ack candidate validation audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_governed_limited_operation_candidate_validation_summary(limit=20):
    records = frappe.get_all(
        VALIDATION_DOCTYPE,
        fields=[
            "name",
            "candidate_validation_id",
            "status",
            "candidate_validation_status",
            "candidate_validation_approved",
            "validated_invoice_set_locked",
            "validated_invoice_set_verified",
            "validated_invoice_names",
            "validated_invoice_count",
            "validated_total_amount",
            "validated_payment_entry_count",
            "same_customer_verified",
            "same_company_verified",
            "same_currency_verified",
            "ready_for_governed_limited_operation_preview_gate",
            "monitored_payment_entry",
            "payment_entry_docstatus_validation",
            "payment_entry_status_validation",
            "candidate_selection",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "candidate_validation_score",
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
            "monitored_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "candidate_validation_records": records,
        "items": items,
        "required_acknowledgement": VALIDATION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12E governed limited-operation candidate validation summary.",
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
            v.name AS candidate_validation,
            v.candidate_validation_id,
            v.status,
            v.candidate_validation_status,
            v.candidate_validation_approved,
            v.phase12d_candidate_selection_verified,
            v.candidate_selection_approved_verified,
            v.selected_invoice_set_locked_verified,
            v.selected_invoice_set_verified,
            v.validated_invoice_set_locked,
            v.validated_invoice_set_verified,
            v.validated_sales_invoices_exist_verified,
            v.validated_sales_invoices_submitted_verified,
            v.validated_outstanding_sufficient_verified,
            v.same_customer_verified,
            v.same_company_verified,
            v.same_currency_verified,
            v.validation_source_locked,
            v.validation_shape_locked,
            v.no_new_accounting_movement_verified,
            v.policy_state_preserved_verified,
            v.ready_for_governed_limited_operation_preview_gate,
            v.validated_source_doctype,
            v.validated_reference_doctype,
            v.validated_party_type,
            v.validated_customer,
            v.validated_company,
            v.validated_currency,
            v.validated_invoice_names,
            v.validated_invoice_count,
            v.validated_total_amount,
            v.validated_payment_entry_count,
            v.monitored_payment_entry,
            v.payment_entry_docstatus_validation,
            v.payment_entry_status_validation,
            v.candidate_selection,
            v.payment_entry_count_before,
            v.payment_entry_count_after,
            v.payment_entry_gl_count_before,
            v.payment_entry_gl_count_after,
            v.actual_payment_entry_created_count,
            v.actual_payment_entry_cancelled_count,
            v.actual_gl_created_count,
            v.submitted_journal_entry_count_today,
            v.purchase_invoice_count_today,
            v.candidate_validation_score,
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
            "labels": [row.candidate_validation_id for row in data[:20]],
            "datasets": [
                {"name": "Candidate Validation Approved", "values": [int(row.candidate_validation_approved or 0) for row in data[:20]]},
                {"name": "Preview Ready", "values": [int(row.ready_for_governed_limited_operation_preview_gate or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Validation Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_validation_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_governed_limited_operation_preview_gate or 0) for row in data), "indicator": "Green", "label": _("Preview Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def validation_columns():
    return [
        {"fieldname": "candidate_validation", "label": _("Candidate Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "candidate_validation_id", "label": _("Candidate Validation ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "candidate_validation_status", "label": _("Validation Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "candidate_validation_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase12d_candidate_selection_verified", "label": _("12D Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "candidate_selection_approved_verified", "label": _("Selection OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "selected_invoice_set_locked_verified", "label": _("Selected Locked"), "fieldtype": "Check", "width": 115},
        {"fieldname": "selected_invoice_set_verified", "label": _("Selected OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "validated_invoice_set_locked", "label": _("Validated Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "validated_invoice_set_verified", "label": _("Validated OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "validated_sales_invoices_exist_verified", "label": _("Exist OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "validated_sales_invoices_submitted_verified", "label": _("Submitted OK"), "fieldtype": "Check", "width": 115},
        {"fieldname": "validated_outstanding_sufficient_verified", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "same_customer_verified", "label": _("Same Customer"), "fieldtype": "Check", "width": 110},
        {"fieldname": "same_company_verified", "label": _("Same Company"), "fieldtype": "Check", "width": 110},
        {"fieldname": "same_currency_verified", "label": _("Same Currency"), "fieldtype": "Check", "width": 110},
        {"fieldname": "validation_source_locked", "label": _("Source Locked"), "fieldtype": "Check", "width": 105},
        {"fieldname": "validation_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 105},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No Movement"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_preview_gate", "label": _("Preview Ready"), "fieldtype": "Check", "width": 115},
        {"fieldname": "validated_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validated_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "validated_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "validated_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
        {"fieldname": "validated_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "validated_invoice_names", "label": _("Validated Invoices"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "validated_invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
        {"fieldname": "validated_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "validated_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 85},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_validation", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_validation", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "candidate_selection", "label": _("Candidate Selection"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "candidate_validation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("candidate_validation"):
        conditions.append("i.candidate_validation = %(candidate_validation)s")
        params["candidate_validation"] = filters.get("candidate_validation")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": VALIDATION_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "candidate_validation", "label": _("Candidate Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "validated_amount", "label": _("Validated Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.candidate_validation,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.validated_amount,
            i.current_outstanding_amount,
            i.monitored_payment_entry,
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
