import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE12H_EXECUTE_GOVERNED_LIMITED_OPERATION_SMOKE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
EXEC_GATE_DOCTYPE = "NDIS Next Governed Limited Op Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Exec Gate Item"
SMOKE_DOCTYPE = "NDIS Next Governed Limited Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Smoke Item"

TEMPLATE_PAYMENT_ENTRY = "ACC-PAY-2026-00011"

EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE = 10
EXPECTED_PAYMENT_ENTRY_COUNT_AFTER = 11
EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE = 62
EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER = 66
EXPECTED_GL_CREATED = 4

EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00

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
    rows = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        filters={
            "status": "Execution Gate Approved",
            "execution_gate_status": "Ready For Governed Limited Operation Smoke",
            "execution_gate_approved": 1,
            "phase12f_preview_verified": 1,
            "preview_approved_verified": 1,
            "preview_reference_set_locked_verified": 1,
            "preview_reference_set_verified": 1,
            "preview_shape_locked_verified": 1,
            "governed_operation_source_locked": 1,
            "governed_operation_shape_locked": 1,
            "approved_reference_set_locked": 1,
            "approved_reference_set_verified": 1,
            "smoke_execution_authorised": 1,
            "smoke_only_authorised": 1,
            "real_production_posting_authorised": 0,
            "live_posting_not_allowed_verified": 1,
            "journal_entry_side_effect_not_allowed_verified": 1,
            "purchase_invoice_side_effect_not_allowed_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_governed_limited_operation_smoke": 1,
            "approved_source_doctype": SMOKE_SOURCE_DOCTYPE,
            "approved_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
            "approved_party_type": SMOKE_PARTY_TYPE,
            "approved_invoice_count": EXPECTED_REFERENCE_COUNT,
            "approved_total_amount": EXPECTED_TOTAL_AMOUNT,
            "approved_payment_entry_count": 1,
            "approved_gl_entry_count_before_smoke": 0,
            "approved_live_posting_allowed": 0,
            "approved_journal_entry_side_effect_allowed": 0,
            "approved_purchase_invoice_side_effect_allowed": 0,
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
        },
        fields=[
            "name",
            "execution_gate_id",
            "approved_source_doctype",
            "approved_reference_doctype",
            "approved_party_type",
            "approved_customer",
            "approved_company",
            "approved_currency",
            "approved_invoice_names",
            "approved_invoice_count",
            "approved_total_amount",
            "approved_payment_entry_count",
            "approved_gl_entry_count_before_smoke",
            "approved_live_posting_allowed",
            "approved_journal_entry_side_effect_allowed",
            "approved_purchase_invoice_side_effect_allowed",
            "smoke_only_authorised",
            "real_production_posting_authorised",
            "approved_reference_set_locked",
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
            "previous_execution_gate",
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
        fields=["name", "smoke_id", "smoke_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def execution_gate_rows(execution_gate):
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
            "current_outstanding_amount",
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
                    "smoke_amount": flt(row.approved_amount or 0, 2),
                    "current_outstanding_amount": flt((si.outstanding_amount if si else row.current_outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "docstatus": int(si.docstatus or 0) if si else None,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def smoke_total(rows):
    return flt(sum(flt(row.smoke_amount or 0, 2) for row in rows), 2)


def outstanding_total(rows):
    return flt(sum(flt(row.current_outstanding_amount or 0, 2) for row in rows), 2)


def all_sales_invoices_exist(rows):
    return int(len(rows) == EXPECTED_REFERENCE_COUNT and all(frappe.db.exists("Sales Invoice", row.reference_name) for row in rows))


def all_sales_invoices_submitted(rows):
    return int(len(rows) == EXPECTED_REFERENCE_COUNT and all(int(row.docstatus or 0) == 1 for row in rows))


def all_outstanding_sufficient(rows):
    return int(len(rows) == EXPECTED_REFERENCE_COUNT and all(flt(row.current_outstanding_amount or 0, 2) >= flt(row.smoke_amount or 0, 2) for row in rows))


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def same_value_verified(rows, fieldname):
    values = set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)])
    return int(len(rows) == EXPECTED_REFERENCE_COUNT and len(values) == 1)


def pe_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def pe_allocated_amount(payment_entry):
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


def create_smoke_payment_entry(rows, notes=None):
    if not frappe.db.exists("Payment Entry", TEMPLATE_PAYMENT_ENTRY):
        frappe.throw(_("Template Payment Entry not found: {0}").format(TEMPLATE_PAYMENT_ENTRY))

    template = frappe.get_doc("Payment Entry", TEMPLATE_PAYMENT_ENTRY)

    if template.docstatus != 2:
        frappe.throw(_("Template Payment Entry must remain cancelled before smoke execution."))

    pe = frappe.copy_doc(template)
    pe.name = None
    pe.docstatus = 0
    pe.status = "Draft"
    pe.posting_date = template.posting_date
    pe.reference_no = f"PHASE12H-{now_datetime().strftime('%Y%m%d%H%M%S')}"
    pe.reference_date = template.reference_date or template.posting_date

    if pe.meta.has_field("amended_from"):
        pe.amended_from = None

    if pe.meta.has_field("clearance_date"):
        pe.clearance_date = None

    if pe.meta.has_field("remarks"):
        pe.remarks = notes or "Phase 12H governed limited-operation smoke Payment Entry"

    pe.references = []

    for row in rows:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": row.reference_name,
                "allocated_amount": flt(row.smoke_amount or 0, 2),
            },
        )

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe.name


def validate_source(execution_gate, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not execution_gate:
        issues.append("No approved Phase 12G execution gate found.")
        return issues

    existing = existing_completed_smoke(execution_gate.name)
    if existing:
        issues.append(f"Completed Phase 12H smoke already exists for this execution gate: {existing.smoke_id} / {existing.smoke_payment_entry}")

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Smoke invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if len(rows) != EXPECTED_REFERENCE_COUNT:
        issues.append(f"Smoke reference count must be {EXPECTED_REFERENCE_COUNT}. Found {len(rows)}.")

    if smoke_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Smoke total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {smoke_total(rows)}.")

    if not all_sales_invoices_exist(rows):
        issues.append("All smoke Sales Invoices must exist.")

    if not all_sales_invoices_submitted(rows):
        issues.append("All smoke Sales Invoices must be submitted.")

    if not all_outstanding_sufficient(rows):
        issues.append("All smoke Sales Invoices must have sufficient outstanding amount before smoke execution.")

    if not same_value_verified(rows, "customer"):
        issues.append("Smoke Sales Invoices must share the same customer.")

    if not same_value_verified(rows, "company"):
        issues.append("Smoke Sales Invoices must share the same company.")

    if not same_value_verified(rows, "currency"):
        issues.append("Smoke Sales Invoices must share the same currency.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE:
        issues.append("Payment Entry count must be 10 before Phase 12H smoke.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE:
        issues.append("Payment Entry GL count must be 62 before Phase 12H smoke.")

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


def build_items(rows, issues, ack_ok, smoke_pe=None):
    items = []

    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Smoke Source",
            "check_key": "smoke_source_valid",
            "check_label": "Smoke source valid",
            "detail": "The Phase 12G execution gate can be used for governed limited-operation smoke execution.",
            "smoke_payment_entry": smoke_pe,
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
                "smoke_payment_entry": smoke_pe,
            })

    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Smoke Reference",
            "check_key": "smoke_sales_invoice_reference",
            "check_label": f"Smoke Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} smoke amount={row.smoke_amount}, outstanding before smoke={row.current_outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "smoke_amount": row.smoke_amount,
            "current_outstanding_amount": row.current_outstanding_amount,
            "smoke_payment_entry": smoke_pe,
        })

    checks = [
        ("smoke_payment_entry_created", "Smoke Payment Entry created", smoke_pe or "None"),
        ("smoke_reference_count", "Smoke reference count", EXPECTED_REFERENCE_COUNT),
        ("smoke_total_amount", "Smoke total amount", EXPECTED_TOTAL_AMOUNT),
        ("smoke_gl_rows", "Smoke GL rows", EXPECTED_GL_CREATED),
        ("rollback_required", "Rollback required", 1),
    ]

    for key, label, value in checks:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Smoke Evidence",
            "check_key": key,
            "check_label": label,
            "detail": f"value={value}",
            "smoke_payment_entry": smoke_pe,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {SMOKE_ACK}",
        "smoke_payment_entry": smoke_pe,
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
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_smoke")

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

    smoke_pe = None
    movement_attempted = 0

    if not int(dry_run or 0) and ack_ok and not source_issues:
        movement_attempted = 1
        smoke_pe = create_smoke_payment_entry(rows, notes=notes)

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

    pe_docstatus = 0
    pe_status = None
    smoke_ref_count = 0
    smoke_amount = 0
    smoke_gl_rows = 0
    smoke_gl_net = 0

    if smoke_pe and frappe.db.exists("Payment Entry", smoke_pe):
        pe = frappe.get_doc("Payment Entry", smoke_pe)
        pe_docstatus = int(pe.docstatus or 0)
        pe_status = pe.status
        smoke_ref_count = pe_reference_count(smoke_pe)
        smoke_amount = pe_allocated_amount(smoke_pe)
        smoke_gl_rows = voucher_gl_rows(smoke_pe)
        smoke_gl_net = voucher_gl_net(smoke_pe)

    post_issues = list(source_issues)

    if movement_attempted:
        if actual_pe_created != 1:
            post_issues.append(f"Smoke must create exactly 1 Payment Entry. Created {actual_pe_created}.")
        if actual_pe_cancelled != 0:
            post_issues.append(f"Smoke must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
        if actual_gl_created != EXPECTED_GL_CREATED:
            post_issues.append(f"Smoke must create {EXPECTED_GL_CREATED} Payment Entry GL rows. Created {actual_gl_created}.")
        if smoke_ref_count != EXPECTED_REFERENCE_COUNT:
            post_issues.append(f"Smoke PE must have {EXPECTED_REFERENCE_COUNT} references. Found {smoke_ref_count}.")
        if smoke_amount != EXPECTED_TOTAL_AMOUNT:
            post_issues.append(f"Smoke PE amount must be {EXPECTED_TOTAL_AMOUNT}. Found {smoke_amount}.")
        if smoke_gl_rows != EXPECTED_GL_CREATED:
            post_issues.append(f"Smoke PE GL rows must be {EXPECTED_GL_CREATED}. Found {smoke_gl_rows}.")
        if smoke_gl_net != 0:
            post_issues.append(f"Smoke PE GL net must be 0.00. Found {smoke_gl_net}.")

    if movement_attempted and guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT_AFTER:
        post_issues.append("Payment Entry count must be 11 after smoke.")

    if movement_attempted and guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER:
        post_issues.append("Payment Entry GL count must be 66 after smoke.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after smoke.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after smoke.")

    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during smoke. This is not allowed.")

    completed = int(
        movement_attempted
        and smoke_pe
        and not post_issues
        and pe_docstatus == 1
        and pe_status == "Submitted"
        and smoke_ref_count == EXPECTED_REFERENCE_COUNT
        and smoke_amount == EXPECTED_TOTAL_AMOUNT
        and smoke_gl_rows == EXPECTED_GL_CREATED
        and smoke_gl_net == 0
        and actual_pe_created == 1
        and actual_pe_cancelled == 0
        and actual_gl_created == EXPECTED_GL_CREATED
        and guard_before["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_BEFORE
        and guard_after["payment_entry_count"] == EXPECTED_PAYMENT_ENTRY_COUNT_AFTER
        and guard_before["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_BEFORE
        and guard_after["payment_entry_gl_count"] == EXPECTED_PAYMENT_ENTRY_GL_COUNT_AFTER
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    )

    items = build_items(rows, post_issues, ack_ok, smoke_pe=smoke_pe)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Smoke Completed - Rollback Required" if completed else "Needs Review",
        "smoke_status": "Governed Limited Operation Smoke Completed" if completed else "Needs Review",
        "smoke_completed": completed,
        "phase12g_execution_gate_verified": 1 if execution_gate else 0,
        "execution_gate_approved_verified": 1 if execution_gate else 0,
        "smoke_only_authorised_verified": int(execution_gate and int(execution_gate.smoke_only_authorised or 0) == 1),
        "real_production_posting_blocked_verified": int(execution_gate and int(execution_gate.real_production_posting_authorised or 0) == 0),
        "approved_reference_set_locked_verified": int(execution_gate and int(execution_gate.approved_reference_set_locked or 0) == 1),
        "approved_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "smoke_payment_entry": smoke_pe,
        "smoke_payment_entry_created": int(bool(smoke_pe)),
        "smoke_payment_entry_submitted": int(pe_docstatus == 1),
        "smoke_payment_entry_docstatus": pe_docstatus,
        "smoke_payment_entry_status": pe_status,
        "smoke_source_doctype": SMOKE_SOURCE_DOCTYPE,
        "smoke_reference_doctype": SMOKE_REFERENCE_DOCTYPE,
        "smoke_party_type": SMOKE_PARTY_TYPE,
        "smoke_customer": unique_value(rows, "customer"),
        "smoke_company": unique_value(rows, "company"),
        "smoke_currency": unique_value(rows, "currency"),
        "smoke_invoice_names": ", ".join(reference_names(rows)),
        "smoke_invoice_count": len(rows),
        "smoke_total_amount": smoke_total(rows),
        "smoke_reference_count": smoke_ref_count,
        "smoke_gl_row_count": smoke_gl_rows,
        "smoke_gl_net": smoke_gl_net,
        "smoke_references_verified": int(smoke_ref_count == EXPECTED_REFERENCE_COUNT),
        "smoke_amount_verified": int(smoke_amount == EXPECTED_TOTAL_AMOUNT),
        "smoke_gl_created_verified": int(smoke_gl_rows == EXPECTED_GL_CREATED),
        "smoke_gl_net_zero_verified": int(smoke_gl_net == 0),
        "journal_entry_side_effect_not_allowed_verified": int(guard_after["submitted_journal_entry_count_today"] == 0),
        "purchase_invoice_side_effect_not_allowed_verified": int(guard_after["purchase_invoice_count_today"] == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "rollback_required": completed,
        "ready_for_governed_limited_operation_rollback": completed,

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
        "actual_policy_mutation_count": policy_mutation_count,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12H executes exactly one governed limited-operation smoke Payment Entry. Rollback is mandatory next.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(SMOKE_DOCTYPE)
    doc.smoke_id = make_smoke_id()

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
        "smoke_payment_entry": smoke_pe,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_smoke_audit(smoke, reason=None):
    assert_action("cancel_governed_limited_operation_smoke_audit")

    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Governed limited-operation smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 12H smoke record."))

    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12H no-ack smoke audit cancelled.",
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
def quick_governed_limited_operation_smoke_summary(limit=20):
    return {
        "smoke_records": frappe.get_all(
            SMOKE_DOCTYPE,
            fields=[
                "name",
                "smoke_id",
                "status",
                "smoke_status",
                "smoke_completed",
                "smoke_payment_entry",
                "smoke_payment_entry_docstatus",
                "smoke_payment_entry_status",
                "smoke_invoice_names",
                "smoke_invoice_count",
                "smoke_total_amount",
                "smoke_reference_count",
                "smoke_gl_row_count",
                "smoke_gl_net",
                "rollback_required",
                "ready_for_governed_limited_operation_rollback",
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
                "smoke_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12H governed limited-operation smoke summary.",
    }


def execute_smoke_report(filters=None):
    columns = [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 440},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 210},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "smoke_payment_entry", "label": _("Smoke PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "smoke_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "smoke_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "smoke_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "smoke_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 80},
        {"fieldname": "smoke_gl_row_count", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 130},
        {"fieldname": "ready_for_governed_limited_operation_rollback", "label": _("Rollback Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
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
            smoke_payment_entry,
            smoke_invoice_names,
            smoke_invoice_count,
            smoke_total_amount,
            smoke_reference_count,
            smoke_gl_row_count,
            smoke_gl_net,
            rollback_required,
            ready_for_governed_limited_operation_rollback,
            payment_entry_count_before,
            payment_entry_count_after,
            payment_entry_gl_count_before,
            payment_entry_gl_count_after,
            actual_payment_entry_created_count,
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
                {"name": "Completed", "values": [int(row.smoke_completed or 0) for row in data[:20]]},
                {"name": "Rollback Ready", "values": [int(row.ready_for_governed_limited_operation_rollback or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Records"), "datatype": "Int"},
        {"value": sum(int(row.smoke_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Orange", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": SMOKE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "smoke_amount", "label": _("Smoke Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding Before"), "fieldtype": "Currency", "width": 140},
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
