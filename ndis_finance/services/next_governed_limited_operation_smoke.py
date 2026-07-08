import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE12T_RUN_NEXT_GOVERNED_LIMITED_OPERATION_SMOKE_CREATE_ONE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
EXECUTION_GATE_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate"
EXECUTION_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Execution Gate Item"
SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"

EXECUTION_READY_FIELD = "ready_for_next_governed_limited_op_smoke"
ROLLBACK_READY_FIELD = "ready_for_next_governed_limited_op_smoke_rollback"

SOURCE_MONITORED_PAYMENT_ENTRY = "ACC-PAY-2026-00012"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE = 11
EXPECTED_PAYMENT_ENTRY_COUNT_AFTER = 12
EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE = 70
EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER = 74

EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_NEW_PAYMENT_ENTRY_COUNT = 1
EXPECTED_NEW_PAYMENT_ENTRY_GL_ROWS = 4
EXPECTED_NEW_PAYMENT_ENTRY_GL_NET = 0.00

SMOKE_SOURCE_DOCTYPE = "Sales Invoice"
SMOKE_REFERENCE_DOCTYPE = "Sales Invoice"
SMOKE_PARTY_TYPE = "Customer"


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
    filters = {
        "status": "Execution Gate Approved",
        "execution_gate_status": "Next Governed Limited Operation Execution Gate Approved",
        "execution_gate_approved": 1,
        "phase12r_preview_verified": 1,
        "preview_approved_verified": 1,
        "preview_source_verified": 1,
        "preview_reference_verified": 1,
        "preview_party_type_verified": 1,
        "preview_reference_set_locked_verified": 1,
        "preview_reference_set_verified": 1,
        "preview_shape_verified": 1,
        "preview_side_effects_blocked_verified": 1,
        "invoice_submission_verified": 1,
        "invoice_outstanding_verified": 1,
        "execution_source_locked": 1,
        "execution_shape_locked": 1,
        "execution_reference_set_locked": 1,
        "execution_reference_set_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "execution_source_doctype": SMOKE_SOURCE_DOCTYPE,
        "execution_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
        "execution_party_type": SMOKE_PARTY_TYPE,
        "execution_invoice_count": EXPECTED_INVOICE_COUNT,
        "execution_total_amount": EXPECTED_TOTAL_AMOUNT,
        "execution_payment_entry_count": 1,
        "execution_gl_entry_count": 0,
        "execution_live_posting_allowed": 0,
        "execution_journal_entry_side_effect_allowed": 0,
        "execution_purchase_invoice_side_effect_allowed": 0,
        "monitored_payment_entry": SOURCE_MONITORED_PAYMENT_ENTRY,
        "monitored_payment_entry_docstatus": 2,
        "monitored_payment_entry_status": "Cancelled",
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

    if has_column(EXECUTION_GATE_DOCTYPE, EXECUTION_READY_FIELD):
        filters[EXECUTION_READY_FIELD] = 1

    rows = frappe.get_all(
        EXECUTION_GATE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "execution_gate_id",
            "execution_source_doctype",
            "execution_reference_doctype",
            "execution_party_type",
            "execution_customer",
            "execution_company",
            "execution_currency",
            "execution_invoice_names",
            "execution_invoice_count",
            "execution_total_amount",
            "execution_payment_entry_count",
            "execution_gl_entry_count",
            "execution_live_posting_allowed",
            "execution_journal_entry_side_effect_allowed",
            "execution_purchase_invoice_side_effect_allowed",
            "execution_reference_set_locked",
            "execution_reference_set_verified",
            "invoice_submission_verified",
            "invoice_outstanding_verified",
            "monitored_payment_entry",
            "monitored_payment_entry_docstatus",
            "monitored_payment_entry_status",
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
            "status": "Completed",
            "smoke_completed": 1,
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
            "category": "Execution Reference",
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
            "execution_amount",
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
            ["docstatus", "customer", "company", "currency", "outstanding_amount", "debit_to"],
            as_dict=True,
        ) if frappe.db.exists("Sales Invoice", row.reference_name) else None

        outstanding = flt((si.outstanding_amount if si else row.current_outstanding_amount) or 0, 2)
        amount = flt(row.execution_amount or 0, 2)

        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "smoke_amount": amount,
                    "current_outstanding_amount": outstanding,
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int((si.docstatus if si else row.invoice_docstatus) or 0),
                    "outstanding_sufficient": int(outstanding >= amount and amount > 0),
                    "debit_to": si.debit_to if si else None,
                    "monitored_payment_entry": row.monitored_payment_entry,
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


def smoke_posting_date():
    if frappe.db.exists("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY):
        return frappe.db.get_value("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY, "posting_date") or today()
    return today()


def get_receipt_account(company):
    company_doc = frappe.get_doc("Company", company)

    for fieldname in ("default_bank_account", "default_cash_account"):
        if company_doc.meta.has_field(fieldname):
            account = company_doc.get(fieldname)
            if account:
                return account

    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 0,
            "account_type": ["in", ["Bank", "Cash"]],
        },
        fields=["name"],
        order_by="account_type desc, name asc",
        limit=1,
    )
    return accounts[0].name if accounts else None


def get_bank_account_for_account(account, company):
    if not account:
        return None
    rows = frappe.get_all(
        "Bank Account",
        filters={"account": account, "company": company},
        fields=["name"],
        order_by="is_default desc, name asc",
        limit=1,
    )
    return rows[0].name if rows else None


def validate_source(execution_gate, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not execution_gate:
        issues.append("No approved Phase 12S next governed limited-operation execution gate found.")
        return issues

    existing = existing_completed_smoke(execution_gate.name)
    if existing:
        issues.append(f"Completed Phase 12T smoke already exists for this execution gate: {existing.smoke_id} / {existing.smoke_payment_entry}")

    if execution_gate.monitored_payment_entry != SOURCE_MONITORED_PAYMENT_ENTRY:
        issues.append(f"Source monitored Payment Entry must be {SOURCE_MONITORED_PAYMENT_ENTRY}.")

    if not frappe.db.exists("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY):
        issues.append(f"Source monitored Payment Entry does not exist: {SOURCE_MONITORED_PAYMENT_ENTRY}")
    else:
        source_pe = frappe.get_doc("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY)
        if int(source_pe.docstatus or 0) != 2 or source_pe.status != "Cancelled":
            issues.append(f"Source monitored Payment Entry must remain Cancelled. Found {source_pe.docstatus} / {source_pe.status}.")

    if execution_gate.execution_source_doctype != SMOKE_SOURCE_DOCTYPE:
        issues.append("Execution source DocType changed.")

    if execution_gate.execution_reference_doctype != SMOKE_REFERENCE_DOCTYPE:
        issues.append("Execution reference DocType changed.")

    if execution_gate.execution_party_type != SMOKE_PARTY_TYPE:
        issues.append("Execution party type changed.")

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
        issues.append("All smoke Sales Invoices must be submitted.")

    if not invoices_outstanding_sufficient(rows):
        issues.append("All smoke Sales Invoices must have sufficient outstanding amount.")

    company = unique_value(rows, "company")
    if company and not get_receipt_account(company):
        issues.append(f"No Bank/Cash receipt account found for company {company}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE:
        issues.append("Payment Entry count must be 11 before smoke.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE:
        issues.append("Payment Entry GL count must be 70 before smoke.")

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
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    return issues


def create_smoke_payment_entry(rows, smoke_id):
    customer = unique_value(rows, "customer")
    company = unique_value(rows, "company")
    currency = unique_value(rows, "currency")
    total = smoke_total(rows)

    if not customer or not company or not currency:
        frappe.throw(_("Smoke invoices must share one customer, company, and currency."))

    paid_from = rows[0].debit_to
    paid_to = get_receipt_account(company)

    if not paid_from:
        frappe.throw(_("Unable to resolve receivable account from Sales Invoice debit_to."))
    if not paid_to:
        frappe.throw(_("Unable to resolve default Bank/Cash account for company {0}.").format(company))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = company
    posting_date = smoke_posting_date()
    pe.posting_date = posting_date
    pe.party_type = "Customer"
    pe.party = customer
    pe.paid_from = paid_from
    pe.paid_to = paid_to
    pe.party_account = paid_from
    bank_account = get_bank_account_for_account(paid_to, company)
    if bank_account:
        pe.bank_account = bank_account
    pe.paid_amount = total
    pe.received_amount = total
    pe.reference_no = smoke_id
    pe.reference_date = posting_date
    pe.remarks = f"Phase 12T next governed limited-operation smoke: {smoke_id}"

    if pe.meta.has_field("source_exchange_rate"):
        pe.source_exchange_rate = 1
    if pe.meta.has_field("target_exchange_rate"):
        pe.target_exchange_rate = 1
    if pe.meta.has_field("paid_from_account_currency"):
        pe.paid_from_account_currency = currency
    if pe.meta.has_field("paid_to_account_currency"):
        pe.paid_to_account_currency = currency

    for row in rows:
        si_values = frappe.db.get_value(
            "Sales Invoice",
            row.reference_name,
            ["grand_total", "outstanding_amount"],
            as_dict=True,
        )
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": row.reference_name,
                "total_amount": flt(si_values.grand_total or 0, 2),
                "outstanding_amount": flt(si_values.outstanding_amount or 0, 2),
                "allocated_amount": flt(row.smoke_amount or 0, 2),
            },
        )

    if hasattr(pe, "set_missing_values"):
        pe.set_missing_values()
    if hasattr(pe, "set_amounts"):
        pe.set_amounts()

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()
    frappe.db.commit()

    return pe.name


def build_items(rows, issues, ack_ok, payment_entry=None, completed=0):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Smoke Source",
            "check_key": "smoke_source_valid",
            "check_label": "Smoke source valid",
            "detail": "The Phase 12S execution gate is stable and the next governed limited-operation smoke can run.",
            "smoke_payment_entry": payment_entry,
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
                "smoke_payment_entry": payment_entry,
            })

    for row in rows:
        item_status = "Pass" if int(row.invoice_docstatus or 0) == 1 and int(row.outstanding_sufficient or 0) == 1 else "Blocker"
        items.append({
            "status": item_status,
            "severity": "High",
            "category": "Smoke Reference",
            "check_key": "smoke_sales_invoice_reference",
            "check_label": f"Smoke Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} smoke amount={row.smoke_amount}, docstatus={row.invoice_docstatus}, outstanding={row.current_outstanding_amount}, sufficient={row.outstanding_sufficient}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "smoke_amount": row.smoke_amount,
            "current_outstanding_amount": row.current_outstanding_amount,
            "invoice_docstatus": row.invoice_docstatus,
            "outstanding_sufficient": row.outstanding_sufficient,
            "smoke_payment_entry": payment_entry,
        })

    checks = [
        ("execution_gate_approved", "Execution gate approved", 1),
        ("smoke_shape", "Smoke shape", f"{EXPECTED_INVOICE_COUNT} / {EXPECTED_TOTAL_AMOUNT} / 1 / 4"),
        ("smoke_payment_entry", "Smoke Payment Entry", payment_entry or "not-created-yet"),
        ("rollback_ready", "Ready for next governed limited-operation smoke rollback", completed),
    ]

    for key, label, value in checks:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Smoke Evidence",
            "check_key": key,
            "check_label": label,
            "detail": f"value={value}",
            "smoke_payment_entry": payment_entry,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {SMOKE_ACK}",
        "smoke_payment_entry": payment_entry,
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
        if item.get("category") != "Smoke Reference":
            continue
        row = frappe.new_doc(SMOKE_ITEM_DOCTYPE)
        row.smoke = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_smoke")

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

    smoke_payment_entry = None
    smoke_id = make_smoke_id()

    if not int(dry_run or 0) and ack_ok and not source_issues:
        smoke_payment_entry = create_smoke_payment_entry(rows, smoke_id)

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

    smoke_pe_docstatus = 0
    smoke_pe_status = None
    smoke_pe_gl_rows = 0
    smoke_pe_gl_net = 0

    if smoke_payment_entry and frappe.db.exists("Payment Entry", smoke_payment_entry):
        pe = frappe.get_doc("Payment Entry", smoke_payment_entry)
        smoke_pe_docstatus = int(pe.docstatus or 0)
        smoke_pe_status = pe.status
        smoke_pe_gl_rows = payment_entry_gl_rows(smoke_payment_entry)
        smoke_pe_gl_net = payment_entry_gl_net(smoke_payment_entry)

    source_pe_docstatus = 0
    source_pe_status = None
    if frappe.db.exists("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY):
        source_pe = frappe.get_doc("Payment Entry", SOURCE_MONITORED_PAYMENT_ENTRY)
        source_pe_docstatus = int(source_pe.docstatus or 0)
        source_pe_status = source_pe.status

    post_issues = list(source_issues)

    expected_pe_created = 0 if int(dry_run or 0) or not ack_ok else 1
    expected_gl_created = 0 if int(dry_run or 0) or not ack_ok else 4

    if actual_pe_created != expected_pe_created:
        post_issues.append(f"Smoke Payment Entry created count mismatch. Expected {expected_pe_created}. Found {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Smoke must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != expected_gl_created:
        post_issues.append(f"Smoke GL created count mismatch. Expected {expected_gl_created}. Found {actual_gl_created}.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during smoke. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and execution_gate
        and smoke_payment_entry
        and not post_issues
        and smoke_pe_docstatus == 1
        and smoke_pe_gl_rows == EXPECTED_NEW_PAYMENT_ENTRY_GL_ROWS
        and smoke_pe_gl_net == EXPECTED_NEW_PAYMENT_ENTRY_GL_NET
        and reference_names(rows) == EXPECTED_INVOICES
        and smoke_total(rows) == EXPECTED_TOTAL_AMOUNT
        and invoices_submitted(rows) == 1
        and invoices_outstanding_sufficient(rows) == 1
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_AFTER
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER
        and actual_pe_created == 1
        and actual_pe_cancelled == 0
        and actual_gl_created == 4
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    execution_source_ok = int(execution_gate and execution_gate.execution_source_doctype == SMOKE_SOURCE_DOCTYPE)
    execution_reference_ok = int(execution_gate and execution_gate.execution_reference_doctype == SMOKE_REFERENCE_DOCTYPE)
    execution_party_ok = int(execution_gate and execution_gate.execution_party_type == SMOKE_PARTY_TYPE)
    execution_shape_ok = int(
        execution_gate
        and int(execution_gate.execution_invoice_count or 0) == EXPECTED_INVOICE_COUNT
        and flt(execution_gate.execution_total_amount or 0, 2) == EXPECTED_TOTAL_AMOUNT
        and int(execution_gate.execution_payment_entry_count or 0) == 1
        and int(execution_gate.execution_gl_entry_count or 0) == 0
    )
    execution_side_effects_ok = int(
        execution_gate
        and int(execution_gate.execution_live_posting_allowed or 0) == 0
        and int(execution_gate.execution_journal_entry_side_effect_allowed or 0) == 0
        and int(execution_gate.execution_purchase_invoice_side_effect_allowed or 0) == 0
    )

    items = build_items(rows, post_issues, ack_ok, payment_entry=smoke_payment_entry, completed=completed)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Completed" if completed else "Needs Review",
        "smoke_status": "Next Governed Limited Operation Smoke Completed" if completed else "Needs Review",
        "smoke_completed": completed,

        "phase12s_execution_gate_verified": 1 if execution_gate else 0,
        "execution_gate_approved_verified": 1 if execution_gate else 0,
        "execution_source_verified": execution_source_ok,
        "execution_reference_verified": execution_reference_ok,
        "execution_party_type_verified": execution_party_ok,
        "execution_reference_set_locked_verified": int(execution_gate and int(execution_gate.execution_reference_set_locked or 0) == 1),
        "execution_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "execution_shape_verified": execution_shape_ok,
        "execution_side_effects_blocked_verified": execution_side_effects_ok,
        "invoice_submission_verified": invoices_submitted(rows),
        "invoice_outstanding_verified": invoices_outstanding_sufficient(rows),
        "smoke_payment_entry_created_verified": int(actual_pe_created == 1 and bool(smoke_payment_entry)),
        "smoke_payment_entry_submitted_verified": int(smoke_pe_docstatus == 1),
        "smoke_gl_rows_verified": int(smoke_pe_gl_rows == EXPECTED_NEW_PAYMENT_ENTRY_GL_ROWS and actual_gl_created == 4),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_unplanned_accounting_movement_verified": int(actual_pe_created == expected_pe_created and actual_pe_cancelled == 0 and actual_gl_created == expected_gl_created),

        "smoke_source_doctype": SMOKE_SOURCE_DOCTYPE,
        "smoke_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
        "smoke_party_type": SMOKE_PARTY_TYPE,
        "smoke_customer": unique_value(rows, "customer"),
        "smoke_company": unique_value(rows, "company"),
        "smoke_currency": unique_value(rows, "currency"),
        "smoke_invoice_names": ", ".join(reference_names(rows)),
        "smoke_invoice_count": len(rows),
        "smoke_total_amount": smoke_total(rows),
        "smoke_payment_entry_count": EXPECTED_NEW_PAYMENT_ENTRY_COUNT if completed else 0,
        "smoke_gl_entry_count": smoke_pe_gl_rows,

        "smoke_payment_entry": smoke_payment_entry,
        "smoke_payment_entry_docstatus": smoke_pe_docstatus,
        "smoke_payment_entry_status": smoke_pe_status,
        "smoke_payment_entry_gl_rows": smoke_pe_gl_rows,
        "smoke_payment_entry_gl_net": smoke_pe_gl_net,

        "source_monitored_payment_entry": SOURCE_MONITORED_PAYMENT_ENTRY,
        "source_monitored_payment_entry_docstatus": source_pe_docstatus,
        "source_monitored_payment_entry_status": source_pe_status,

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

        ROLLBACK_READY_FIELD: completed,

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
        "note": "Phase 12T creates exactly one governed smoke Payment Entry and four Payment Entry GL rows.",
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
        "smoke_payment_entry": smoke_payment_entry,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_smoke_audit(smoke, reason=None):
    assert_action("cancel_next_governed_limited_operation_smoke_audit")

    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Next governed limited-operation smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 12T smoke record. Use the rollback phase instead."))

    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12T no-ack smoke audit cancelled.",
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
def quick_next_governed_limited_operation_smoke_summary(limit=20):
    return {
        "smoke_records": frappe.get_all(
            SMOKE_DOCTYPE,
            fields=[
                "name",
                "smoke_id",
                "status",
                "smoke_status",
                "smoke_completed",
                "smoke_invoice_names",
                "smoke_invoice_count",
                "smoke_total_amount",
                "smoke_payment_entry",
                "smoke_payment_entry_docstatus",
                "smoke_payment_entry_status",
                "smoke_payment_entry_gl_rows",
                "smoke_payment_entry_gl_net",
                "payment_entry_count_before",
                "payment_entry_count_after",
                "payment_entry_gl_count_before",
                "payment_entry_gl_count_after",
                "actual_payment_entry_created_count",
                "actual_payment_entry_cancelled_count",
                "actual_gl_created_count",
                "submitted_journal_entry_count_today",
                "purchase_invoice_count_today",
                ROLLBACK_READY_FIELD,
                "checked_on",
                "checked_by",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.get_all(
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
                "smoke_amount",
                "current_outstanding_amount",
                "invoice_docstatus",
                "outstanding_sufficient",
                "smoke_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12T next governed limited-operation smoke summary.",
    }


def execute_smoke_report(filters=None):
    columns = [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 460},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "smoke_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "smoke_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 105},
        {"fieldname": "smoke_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "smoke_payment_entry", "label": _("Smoke PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "smoke_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "smoke_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "smoke_payment_entry_gl_rows", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": ROLLBACK_READY_FIELD, "label": _("Rollback Ready"), "fieldtype": "Check", "width": 120},
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
            smoke_invoice_names,
            smoke_invoice_count,
            smoke_total_amount,
            smoke_payment_entry,
            smoke_payment_entry_docstatus,
            smoke_payment_entry_status,
            smoke_payment_entry_gl_rows,
            `{ROLLBACK_READY_FIELD}` AS `{ROLLBACK_READY_FIELD}`,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_gl_created_count,
            checked_on
        FROM `tab{SMOKE_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_id for row in data[:20]],
            "datasets": [
                {"name": "Smoke Completed", "values": [int(row.smoke_completed or 0) for row in data[:20]]},
                {"name": "Rollback Ready", "values": [int(row.get(ROLLBACK_READY_FIELD) or 0) for row in data[:20]]},
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
        {"fieldname": "smoke_amount", "label": _("Smoke Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "invoice_docstatus", "label": _("Invoice Docstatus"), "fieldtype": "Int", "width": 120},
        {"fieldname": "outstanding_sufficient", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "smoke_payment_entry", "label": _("Smoke PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
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
            current_outstanding_amount,
            invoice_docstatus,
            outstanding_sufficient,
            smoke_payment_entry,
            check_label,
            detail
        FROM `tab{SMOKE_ITEM_DOCTYPE}`
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
        {"value": len([row for row in data if row.category == "Smoke Reference"]), "indicator": "Green", "label": _("Smoke References"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary