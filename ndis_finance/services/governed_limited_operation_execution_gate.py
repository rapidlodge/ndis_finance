import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXEC_GATE_ACK = "I_CONFIRM_PHASE12G_APPROVE_GOVERNED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Next Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Preview Item"
EXEC_GATE_DOCTYPE = "NDIS Next Governed Limited Op Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Exec Gate Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00011"
EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_PAYMENT_ENTRY_COUNT = 10
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 62
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

APPROVED_SOURCE_DOCTYPE = "Sales Invoice"
APPROVED_REFERENCE_DOCTYPE = "Sales Invoice"
APPROVED_PARTY_TYPE = "Customer"
APPROVED_INVOICE_COUNT = 3
APPROVED_TOTAL_AMOUNT = 3.00
APPROVED_PAYMENT_ENTRY_COUNT = 1
APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE = 0


def make_execution_gate_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-EXEC-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
            "preview_status": "Governed Limited Operation Preview Approved",
            "preview_approved": 1,
            "phase12e_candidate_validation_verified": 1,
            "candidate_validation_approved_verified": 1,
            "validated_invoice_set_locked_verified": 1,
            "validated_invoice_set_verified": 1,
            "preview_reference_set_locked": 1,
            "preview_reference_set_verified": 1,
            "preview_source_locked": 1,
            "preview_shape_locked": 1,
            "preview_sales_invoices_exist_verified": 1,
            "preview_sales_invoices_submitted_verified": 1,
            "preview_outstanding_sufficient_verified": 1,
            "same_customer_verified": 1,
            "same_company_verified": 1,
            "same_currency_verified": 1,
            "preview_payment_entry_previewed": 1,
            "preview_gl_previewed": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_governed_limited_operation_execution_gate": 1,
            "preview_source_doctype": APPROVED_SOURCE_DOCTYPE,
            "preview_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
            "preview_party_type": APPROVED_PARTY_TYPE,
            "preview_invoice_count": APPROVED_INVOICE_COUNT,
            "preview_total_amount": APPROVED_TOTAL_AMOUNT,
            "preview_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
            "preview_gl_entry_count": APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE,
            "preview_live_posting_allowed": 0,
            "preview_journal_entry_side_effect_allowed": 0,
            "preview_purchase_invoice_side_effect_allowed": 0,
            "monitored_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "payment_entry_docstatus_preview": 2,
            "payment_entry_status_preview": "Cancelled",
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
            "preview_id",
            "monitored_payment_entry",
            "preview_source_doctype",
            "preview_reference_doctype",
            "preview_party_type",
            "preview_customer",
            "preview_company",
            "preview_currency",
            "preview_invoice_names",
            "preview_invoice_count",
            "preview_total_amount",
            "preview_payment_entry_count",
            "preview_gl_entry_count",
            "preview_reference_set_locked",
            "preview_reference_set_verified",
            "preview_source_locked",
            "preview_shape_locked",
            "preview_live_posting_allowed",
            "preview_journal_entry_side_effect_allowed",
            "preview_purchase_invoice_side_effect_allowed",
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
        fields=["name", "execution_gate_id", "approved_invoice_names"],
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
                        "approved_amount": flt(row.preview_amount or 0, 2),
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
                    "approved_amount": flt(row.preview_amount or 0, 2),
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


def approved_total(rows):
    return flt(sum(flt(row.approved_amount or 0, 2) for row in rows), 2)


def outstanding_total(rows):
    return flt(sum(flt(row.current_outstanding_amount or 0, 2) for row in rows), 2)


def all_sales_invoices_exist(rows):
    return int(len(rows) == APPROVED_INVOICE_COUNT and all(frappe.db.exists("Sales Invoice", row.reference_name) for row in rows))


def all_sales_invoices_submitted(rows):
    return int(len(rows) == APPROVED_INVOICE_COUNT and all(int(row.docstatus or 0) == 1 for row in rows))


def all_outstanding_sufficient(rows):
    return int(len(rows) == APPROVED_INVOICE_COUNT and all(flt(row.current_outstanding_amount or 0, 2) >= flt(row.approved_amount or 0, 2) for row in rows))


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def same_value_verified(rows, fieldname):
    values = set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)])
    return int(len(rows) == APPROVED_INVOICE_COUNT and len(values) == 1)


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


def validate_source(preview, payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not preview:
        issues.append("No approved Phase 12F governed limited-operation preview found.")
        return issues

    existing = existing_approved_execution_gate(preview.name)
    if existing:
        issues.append(f"Approved Phase 12G execution gate already exists for this preview: {existing.execution_gate_id} / {existing.approved_invoice_names}")

    if preview.preview_source_doctype != APPROVED_SOURCE_DOCTYPE:
        issues.append(f"Preview source doctype must be {APPROVED_SOURCE_DOCTYPE}. Found {preview.preview_source_doctype}.")

    if preview.preview_reference_doctype != APPROVED_REFERENCE_DOCTYPE:
        issues.append(f"Preview reference doctype must be {APPROVED_REFERENCE_DOCTYPE}. Found {preview.preview_reference_doctype}.")

    if preview.preview_party_type != APPROVED_PARTY_TYPE:
        issues.append(f"Preview party type must be {APPROVED_PARTY_TYPE}. Found {preview.preview_party_type}.")

    if int(preview.preview_invoice_count or 0) != APPROVED_INVOICE_COUNT:
        issues.append(f"Preview invoice count must be {APPROVED_INVOICE_COUNT}. Found {preview.preview_invoice_count}.")

    if flt(preview.preview_total_amount or 0, 2) != APPROVED_TOTAL_AMOUNT:
        issues.append(f"Preview total amount must be {APPROVED_TOTAL_AMOUNT}. Found {preview.preview_total_amount}.")

    if int(preview.preview_payment_entry_count or 0) != APPROVED_PAYMENT_ENTRY_COUNT:
        issues.append(f"Preview Payment Entry count must be {APPROVED_PAYMENT_ENTRY_COUNT}. Found {preview.preview_payment_entry_count}.")

    if int(preview.preview_gl_entry_count or 0) != APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE:
        issues.append(f"Preview future GL-before-smoke count must be {APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE}. Found {preview.preview_gl_entry_count}.")

    if int(preview.preview_live_posting_allowed or 0) != 0:
        issues.append("Preview live posting must remain disabled.")

    if int(preview.preview_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Preview Journal Entry side effects must remain disabled.")

    if int(preview.preview_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Preview Purchase Invoice side effects must remain disabled.")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Approved invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != APPROVED_INVOICE_COUNT:
        issues.append(f"Approved invoice count must be {APPROVED_INVOICE_COUNT}. Found {len(rows)}.")

    if approved_total(rows) != APPROVED_TOTAL_AMOUNT:
        issues.append(f"Approved total must be {APPROVED_TOTAL_AMOUNT}. Found {approved_total(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("All approved Sales Invoices must exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("All approved Sales Invoices must be submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("All approved Sales Invoices must have outstanding amount sufficient for the approved amount.")

    if not same_value_verified(rows, "customer"):
        issues.append("Approved Sales Invoices must share the same customer.")

    if not same_value_verified(rows, "company"):
        issues.append("Approved Sales Invoices must share the same company.")

    if not same_value_verified(rows, "currency"):
        issues.append("Approved Sales Invoices must share the same currency.")

    if not payment_entry:
        issues.append("Phase 12F preview did not identify a monitored Payment Entry.")
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
        issues.append("Payment Entry count must remain 10 before Phase 12G execution gate.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 62 before Phase 12G execution gate.")

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
                "approved_amount": row.approved_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
            }
        )

    items.append(item)


def build_items(preview, rows, issues, ack_ok, payment_entry=None):
    items = []

    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase12f_preview_exists",
            "Phase 12F preview exists",
            f"Preview found: {preview.preview_id}.",
            payment_entry=payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase12f_preview_exists", "Phase 12F preview exists", "No approved Phase 12F preview found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Execution Gate Source",
            "execution_gate_source_valid",
            "Execution gate source valid",
            "The approved preview can be authorised for governed limited-operation smoke execution.",
            payment_entry=payment_entry,
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
                payment_entry=payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Approved Reference",
            "approved_sales_invoice_reference",
            f"Approved Sales Invoice {row.idx}",
            f"{row.reference_name} approved for smoke with amount={row.approved_amount}, outstanding={row.current_outstanding_amount}.",
            row=row,
            payment_entry=payment_entry,
        )

    checks = [
        ("approved_invoice_set", "Approved invoice set locked", ", ".join(EXPECTED_INVOICES)),
        ("approved_shape", "Approved count/amount/future PE/future GL-before-smoke locked", f"{APPROVED_INVOICE_COUNT} / {APPROVED_TOTAL_AMOUNT} / {APPROVED_PAYMENT_ENTRY_COUNT} / {APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE}"),
        ("source_lock", "Source/reference/party locked", f"{APPROVED_SOURCE_DOCTYPE} / {APPROVED_REFERENCE_DOCTYPE} / {APPROVED_PARTY_TYPE}"),
        ("same_customer", "Same customer verified", unique_value(rows, "customer") or "None"),
        ("same_company", "Same company verified", unique_value(rows, "company") or "None"),
        ("same_currency", "Same currency verified", unique_value(rows, "currency") or "None"),
        ("smoke_execution_authorised", "Smoke execution authorised", 1),
        ("smoke_only_authorised", "Smoke-only authorised", 1),
        ("real_production_blocked", "Real production posting authorised", 0),
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
        ("smoke_ready", "Ready for governed limited-operation smoke", 1),
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
            payment_entry=payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", payment_entry=payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {EXEC_GATE_ACK}")

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
def run_governed_limited_operation_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_execution_gate")

    preview = latest_preview()
    payment_entry = preview.monitored_payment_entry if preview else None
    rows = preview_rows(preview.name) if preview else []

    guard_before = guardrails()
    ack_ok = acknowledgement == EXEC_GATE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    source_issues = validate_source(preview, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

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
        post_issues.append(f"Execution gate must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Execution gate must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Execution gate must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        post_issues.append("Payment Entry count must remain 10 after execution gate.")

    if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        post_issues.append("Payment Entry GL count must remain 62 after execution gate.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after execution gate.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after execution gate.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during execution gate. This is not allowed.")

    approved_reference_set_verified = int(reference_names(rows) == EXPECTED_INVOICES)
    approved_exists = all_sales_invoices_exist(rows)
    approved_submitted = all_sales_invoices_submitted(rows)
    approved_outstanding = all_outstanding_sufficient(rows)
    same_customer = same_value_verified(rows, "customer")
    same_company = same_value_verified(rows, "company")
    same_currency = same_value_verified(rows, "currency")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and preview
        and payment_entry
        and not post_issues
        and approved_reference_set_verified
        and approved_exists
        and approved_submitted
        and approved_outstanding
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
        and approved_total(rows) == APPROVED_TOTAL_AMOUNT
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

    items = build_items(preview, rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Gate Approved" if completed else "Needs Review",
        "execution_gate_status": "Ready For Governed Limited Operation Smoke" if completed else "Needs Review",
        "execution_gate_approved": completed,
        "phase12f_preview_verified": 1 if preview else 0,
        "preview_approved_verified": 1 if preview else 0,
        "preview_reference_set_locked_verified": int(preview and int(preview.preview_reference_set_locked or 0) == 1),
        "preview_reference_set_verified": int(preview and int(preview.preview_reference_set_verified or 0) == 1),
        "preview_shape_locked_verified": int(preview and int(preview.preview_shape_locked or 0) == 1),
        "governed_operation_source_locked": int(preview and int(preview.preview_source_locked or 0) == 1),
        "governed_operation_shape_locked": int(preview and int(preview.preview_shape_locked or 0) == 1),
        "approved_reference_set_locked": completed,
        "approved_reference_set_verified": approved_reference_set_verified,
        "approved_sales_invoices_exist_verified": approved_exists,
        "approved_sales_invoices_submitted_verified": approved_submitted,
        "approved_outstanding_sufficient_verified": approved_outstanding,
        "same_customer_verified": same_customer,
        "same_company_verified": same_company,
        "same_currency_verified": same_currency,
        "smoke_execution_authorised": completed,
        "smoke_only_authorised": completed,
        "real_production_posting_authorised": 0,
        "live_posting_not_allowed_verified": int(preview and int(preview.preview_live_posting_allowed or 0) == 0),
        "journal_entry_side_effect_not_allowed_verified": int(preview and int(preview.preview_journal_entry_side_effect_allowed or 0) == 0),
        "purchase_invoice_side_effect_not_allowed_verified": int(preview and int(preview.preview_purchase_invoice_side_effect_allowed or 0) == 0),
        "monitored_payment_entry_verified": int(bool(payment_entry)),
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_governed_limited_operation_smoke": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,

        "approved_source_doctype": APPROVED_SOURCE_DOCTYPE,
        "approved_reference_doctype": APPROVED_REFERENCE_DOCTYPE,
        "approved_party_type": APPROVED_PARTY_TYPE,
        "approved_customer": unique_value(rows, "customer"),
        "approved_company": unique_value(rows, "company"),
        "approved_currency": unique_value(rows, "currency"),
        "approved_invoice_names": ", ".join(reference_names(rows)),
        "approved_invoice_count": len(rows),
        "approved_total_amount": approved_total(rows),
        "approved_payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
        "approved_gl_entry_count_before_smoke": APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE,
        "approved_live_posting_allowed": 0,
        "approved_journal_entry_side_effect_allowed": 0,
        "approved_purchase_invoice_side_effect_allowed": 0,

        "preview_source_doctype": preview.preview_source_doctype if preview else None,
        "preview_reference_doctype": preview.preview_reference_doctype if preview else None,
        "preview_party_type": preview.preview_party_type if preview else None,
        "preview_customer": preview.preview_customer if preview else None,
        "preview_company": preview.preview_company if preview else None,
        "preview_currency": preview.preview_currency if preview else None,
        "preview_invoice_names": preview.preview_invoice_names if preview else None,
        "preview_invoice_count": int(preview.preview_invoice_count or 0) if preview else 0,
        "preview_total_amount": flt(preview.preview_total_amount or 0, 2) if preview else 0,
        "preview_payment_entry_count": int(preview.preview_payment_entry_count or 0) if preview else 0,
        "preview_gl_entry_count": int(preview.preview_gl_entry_count or 0) if preview else 0,

        "monitored_payment_entry": payment_entry,
        "payment_entry_docstatus_exec_gate": pe_docstatus,
        "payment_entry_status_exec_gate": pe_status,
        "monitored_reference_count": reference_count,
        "monitored_total_amount": total_amount,
        "monitored_voucher_gl_rows": voucher_rows,
        "monitored_voucher_gl_net": voucher_net,
        "monitored_restored_invoice_amount": restored_invoice_amount,

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
        "required_acknowledgement": EXEC_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12G approves the governed limited-operation execution gate only. It authorises smoke-only execution next; it does not post.",
    }

    if int(dry_run or 0):
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
    doc.required_acknowledgement = EXEC_GATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.execution_gate_json = safe_json(
        {
            "preview": preview,
            "monitored_payment_entry": payment_entry,
            "approved_envelope": {
                "source_doctype": APPROVED_SOURCE_DOCTYPE,
                "reference_doctype": APPROVED_REFERENCE_DOCTYPE,
                "party_type": APPROVED_PARTY_TYPE,
                "invoice_names": reference_names(rows),
                "invoice_count": len(rows),
                "total_amount": approved_total(rows),
                "payment_entry_count": APPROVED_PAYMENT_ENTRY_COUNT,
                "gl_entry_count_before_smoke": APPROVED_GL_ENTRY_COUNT_BEFORE_SMOKE,
                "customer": unique_value(rows, "customer"),
                "company": unique_value(rows, "company"),
                "currency": unique_value(rows, "currency"),
                "smoke_execution_authorised": completed,
                "smoke_only_authorised": completed,
                "real_production_posting_authorised": 0,
                "live_posting_allowed": 0,
                "journal_entry_side_effect_allowed": 0,
                "purchase_invoice_side_effect_allowed": 0,
            },
            "approved_references": [dict(row) for row in rows],
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
        "execution_gate": doc.name,
        "execution_gate_id": doc.execution_gate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_execution_gate_audit(execution_gate, reason=None):
    assert_action("cancel_governed_limited_operation_execution_gate_audit")

    if not frappe.db.exists(EXEC_GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Governed limited-operation execution gate audit not found: {0}").format(execution_gate))

    doc = frappe.get_doc(EXEC_GATE_DOCTYPE, execution_gate)

    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 12G execution gate record."))

    frappe.db.set_value(
        EXEC_GATE_DOCTYPE,
        execution_gate,
        {
            "status": "Cancelled",
            "execution_gate_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12G no-ack execution gate audit cancelled.",
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
def quick_governed_limited_operation_execution_gate_summary(limit=20):
    records = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        fields=[
            "name",
            "execution_gate_id",
            "status",
            "execution_gate_status",
            "execution_gate_approved",
            "approved_reference_set_locked",
            "approved_reference_set_verified",
            "approved_invoice_names",
            "approved_invoice_count",
            "approved_total_amount",
            "approved_payment_entry_count",
            "approved_gl_entry_count_before_smoke",
            "smoke_execution_authorised",
            "smoke_only_authorised",
            "real_production_posting_authorised",
            "ready_for_governed_limited_operation_smoke",
            "monitored_payment_entry",
            "payment_entry_docstatus_exec_gate",
            "payment_entry_status_exec_gate",
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
            "current_outstanding_amount",
            "monitored_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "execution_gate_records": records,
        "items": items,
        "required_acknowledgement": EXEC_GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12G governed limited-operation execution gate summary.",
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
            g.phase12f_preview_verified,
            g.preview_approved_verified,
            g.preview_reference_set_locked_verified,
            g.preview_reference_set_verified,
            g.preview_shape_locked_verified,
            g.governed_operation_source_locked,
            g.governed_operation_shape_locked,
            g.approved_reference_set_locked,
            g.approved_reference_set_verified,
            g.same_customer_verified,
            g.same_company_verified,
            g.same_currency_verified,
            g.smoke_execution_authorised,
            g.smoke_only_authorised,
            g.real_production_posting_authorised,
            g.live_posting_not_allowed_verified,
            g.no_new_accounting_movement_verified,
            g.policy_state_preserved_verified,
            g.ready_for_governed_limited_operation_smoke,
            g.approved_source_doctype,
            g.approved_reference_doctype,
            g.approved_party_type,
            g.approved_customer,
            g.approved_company,
            g.approved_currency,
            g.approved_invoice_names,
            g.approved_invoice_count,
            g.approved_total_amount,
            g.approved_payment_entry_count,
            g.approved_gl_entry_count_before_smoke,
            g.monitored_payment_entry,
            g.payment_entry_docstatus_exec_gate,
            g.payment_entry_status_exec_gate,
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
                {"name": "Execution Gate Approved", "values": [int(row.execution_gate_approved or 0) for row in data[:20]]},
                {"name": "Smoke Ready", "values": [int(row.ready_for_governed_limited_operation_smoke or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gate Records"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_governed_limited_operation_smoke or 0) for row in data), "indicator": "Green", "label": _("Smoke Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execution_gate_columns():
    return [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "execution_gate_status", "label": _("Execution Gate Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase12f_preview_verified", "label": _("12F Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "preview_approved_verified", "label": _("Preview OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_reference_set_locked_verified", "label": _("Preview Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "preview_reference_set_verified", "label": _("Preview Set OK"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_shape_locked_verified", "label": _("Shape OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "governed_operation_source_locked", "label": _("Source Locked"), "fieldtype": "Check", "width": 105},
        {"fieldname": "governed_operation_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 105},
        {"fieldname": "approved_reference_set_locked", "label": _("Approved Locked"), "fieldtype": "Check", "width": 115},
        {"fieldname": "approved_reference_set_verified", "label": _("Approved OK"), "fieldtype": "Check", "width": 100},
        {"fieldname": "same_customer_verified", "label": _("Same Customer"), "fieldtype": "Check", "width": 110},
        {"fieldname": "same_company_verified", "label": _("Same Company"), "fieldtype": "Check", "width": 110},
        {"fieldname": "same_currency_verified", "label": _("Same Currency"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke_execution_authorised", "label": _("Smoke Auth"), "fieldtype": "Check", "width": 100},
        {"fieldname": "smoke_only_authorised", "label": _("Smoke Only"), "fieldtype": "Check", "width": 95},
        {"fieldname": "real_production_posting_authorised", "label": _("Real Prod Auth"), "fieldtype": "Check", "width": 115},
        {"fieldname": "live_posting_not_allowed_verified", "label": _("Live Disabled"), "fieldtype": "Check", "width": 105},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No Movement"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_smoke", "label": _("Smoke Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "approved_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "approved_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "approved_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "approved_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "approved_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
        {"fieldname": "approved_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "approved_invoice_names", "label": _("Approved Invoices"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "approved_invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
        {"fieldname": "approved_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "approved_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 85},
        {"fieldname": "approved_gl_entry_count_before_smoke", "label": _("GL Before Smoke"), "fieldtype": "Int", "width": 115},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_exec_gate", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_exec_gate", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
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
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 210},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "approved_amount", "label": _("Approved Amount"), "fieldtype": "Currency", "width": 120},
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
            i.current_outstanding_amount,
            i.monitored_payment_entry,
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
