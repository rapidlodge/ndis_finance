import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE12O_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_DESIGN_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"
DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00012"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
EXPECTED_PAYMENT_ENTRY_COUNT = 11
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 70
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_VOUCHER_GL_NET = 0.00
EXPECTED_REVERSAL_GL_ROWS = 4

DESIGN_SOURCE_DOCTYPE = "Sales Invoice"
DESIGN_REFERENCE_DOCTYPE = "Sales Invoice"
DESIGN_PARTY_TYPE = "Customer"
DESIGN_PAYMENT_ENTRY_COUNT = 1
DESIGN_GL_ENTRY_COUNT = 0


def make_design_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


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


def latest_planning():
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={
            "status": "Planning Approved",
            "planning_status": "Next Governed Limited Operation Planning Approved",
            "planning_approved": 1,
            "phase12m_runtime_monitor_verified": 1,
            "runtime_monitor_active_verified": 1,
            "monitored_payment_entry_verified": 1,
            "payment_entry_cancelled_still_verified": 1,
            "voucher_gl_rows_verified": 1,
            "voucher_gl_net_zero_verified": 1,
            "reversal_gl_rows_verified": 1,
            "restored_invoice_amount_verified": 1,
            "payment_entry_count_stable_verified": 1,
            "payment_entry_gl_count_stable_verified": 1,
            "policy_state_preserved_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "planned_source_doctype": DESIGN_SOURCE_DOCTYPE,
            "planned_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
            "planned_party_type": DESIGN_PARTY_TYPE,
            "planned_invoice_count": EXPECTED_INVOICE_COUNT,
            "planned_total_amount": EXPECTED_TOTAL_AMOUNT,
            "planned_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
            "planned_gl_entry_count": DESIGN_GL_ENTRY_COUNT,
            "planned_live_posting_allowed": 0,
            "planned_journal_entry_side_effect_allowed": 0,
            "planned_purchase_invoice_side_effect_allowed": 0,
            "ready_for_next_governed_limited_operation_design_gate": 1,
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
        },
        fields=[
            "name",
            "planning_id",
            "planned_source_doctype",
            "planned_reference_doctype",
            "planned_party_type",
            "planned_customer",
            "planned_company",
            "planned_currency",
            "planned_invoice_names",
            "planned_invoice_count",
            "planned_total_amount",
            "planned_payment_entry_count",
            "planned_gl_entry_count",
            "planned_live_posting_allowed",
            "planned_journal_entry_side_effect_allowed",
            "planned_purchase_invoice_side_effect_allowed",
            "monitored_payment_entry",
            "monitored_payment_entry_docstatus",
            "monitored_payment_entry_status",
            "monitored_voucher_gl_rows",
            "monitored_voucher_gl_net",
            "monitored_reversal_gl_rows",
            "monitored_restored_invoice_amount",
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
            "design",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_design(planning):
    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={"planning": planning, "status": "Design Approved", "design_approved": 1},
        fields=["name", "design_id", "design_invoice_names"],
        limit=1,
    )
    return rows[0] if rows else None


def planning_rows(planning):
    rows = frappe.get_all(
        PLANNING_ITEM_DOCTYPE,
        filters={
            "planning": planning,
            "category": "Planned Reference",
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
            "planned_amount",
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
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "design_amount": flt(row.planned_amount or 0, 2),
                    "current_outstanding_amount": flt((si.outstanding_amount if si else 0) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "docstatus": int(si.docstatus or 0) if si else None,
                    "monitored_payment_entry": row.monitored_payment_entry,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def design_total(rows):
    return flt(sum(flt(row.design_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set(getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)))
    return values[0] if len(values) == 1 else None


def same_value_verified(rows, fieldname):
    values = set(getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None))
    return int(len(rows) == EXPECTED_INVOICE_COUNT and len(values) == 1)


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


def validate_source(planning, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not planning:
        issues.append("No approved Phase 12N next governed limited-operation planning found.")
        return issues

    existing = existing_approved_design(planning.name)
    if existing:
        issues.append(f"Approved Phase 12O design already exists for this planning: {existing.design_id} / {existing.design_invoice_names}")

    payment_entry = planning.monitored_payment_entry
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

    if planning.planned_source_doctype != DESIGN_SOURCE_DOCTYPE:
        issues.append("Planned source DocType changed.")
    if planning.planned_reference_doctype != DESIGN_REFERENCE_DOCTYPE:
        issues.append("Planned reference DocType changed.")
    if planning.planned_party_type != DESIGN_PARTY_TYPE:
        issues.append("Planned party type changed.")
    if int(planning.planned_payment_entry_count or 0) != DESIGN_PAYMENT_ENTRY_COUNT:
        issues.append("Planned Payment Entry count must be 1.")
    if int(planning.planned_gl_entry_count or 0) != DESIGN_GL_ENTRY_COUNT:
        issues.append("Planned GL count must be 0 before execution.")
    if int(planning.planned_live_posting_allowed or 0) != 0:
        issues.append("Planning live posting allowed must remain 0.")
    if int(planning.planned_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Planning Journal Entry side effect allowed must remain 0.")
    if int(planning.planned_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Planning Purchase Invoice side effect allowed must remain 0.")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Design invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Design invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if design_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Design total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {design_total(rows)}.")
    if not same_value_verified(rows, "customer"):
        issues.append("Designed Sales Invoices must share the same customer.")
    if not same_value_verified(rows, "company"):
        issues.append("Designed Sales Invoices must share the same company.")
    if not same_value_verified(rows, "currency"):
        issues.append("Designed Sales Invoices must share the same currency.")
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
        issues.append("Payment Entry count must remain 11 before design.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 70 before design.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before design.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before design.")
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
                "category": "Design Source",
                "check_key": "design_source_valid",
                "check_label": "Design source valid",
                "detail": "The Phase 12N planning gate is stable and can be locked as the next governed limited-operation design.",
                "monitored_payment_entry": payment_entry,
            }
        )
    else:
        for issue in issues:
            items.append(
                {
                    "status": "Blocker",
                    "severity": "Critical",
                    "category": "Design Source",
                    "check_key": "design_source_valid",
                    "check_label": "Design source valid",
                    "detail": issue,
                    "monitored_payment_entry": payment_entry,
                }
            )

    for row in rows:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Designed Reference",
                "check_key": "designed_sales_invoice_reference",
                "check_label": f"Designed Sales Invoice {row.idx}",
                "detail": f"{row.reference_name} design amount={row.design_amount}, outstanding={row.current_outstanding_amount}.",
                "line_no": row.idx,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "design_amount": row.design_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
                "monitored_payment_entry": payment_entry,
            }
        )

    checks = [
        ("planning_approved", "Planning approved", 1),
        ("design_source_locked", "Design source/reference/party", f"{DESIGN_SOURCE_DOCTYPE} / {DESIGN_REFERENCE_DOCTYPE} / {DESIGN_PARTY_TYPE}"),
        ("design_shape_locked", "Design shape", f"{EXPECTED_INVOICE_COUNT} / {EXPECTED_TOTAL_AMOUNT} / {DESIGN_PAYMENT_ENTRY_COUNT} / {DESIGN_GL_ENTRY_COUNT}"),
        ("design_side_effects", "Design live/JE/PI side effects", "0 / 0 / 0"),
        ("candidate_selection_not_started", "Candidate selection not started", 1),
        ("candidate_selection_gate_ready", "Ready for next governed limited-operation candidate selection gate", 1),
    ]
    for key, label, value in checks:
        items.append(
            {
                "status": "Pass",
                "severity": "High",
                "category": "Design Evidence",
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
            "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {DESIGN_ACK}",
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
        row = frappe.new_doc(DESIGN_ITEM_DOCTYPE)
        row.design = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_design(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_design")

    planning = latest_planning()
    rows = planning_rows(planning.name) if planning else []
    payment_entry = planning.monitored_payment_entry if planning else None
    guard_before = guardrails()
    ack_ok = acknowledgement == DESIGN_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0
    source_issues = validate_source(planning, rows, guard_before, config, policy_enabled_before, policy_live_before)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "production_batch_enabled") if planning else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, planning.target_policy, "live_posting_allowed") if planning else 0
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
        post_issues.append(f"Design must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Design must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Design must create 0 GL rows. Created {actual_gl_created}.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during design. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and planning
        and payment_entry
        and not post_issues
        and pe_docstatus == 2
        and pe_status == "Cancelled"
        and reference_names(rows) == EXPECTED_INVOICES
        and design_total(rows) == EXPECTED_TOTAL_AMOUNT
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
    planned_source_ok = int(planning and planning.planned_source_doctype == DESIGN_SOURCE_DOCTYPE)
    planned_reference_ok = int(planning and planning.planned_reference_doctype == DESIGN_REFERENCE_DOCTYPE)
    planned_party_ok = int(planning and planning.planned_party_type == DESIGN_PARTY_TYPE)
    planned_shape_ok = int(
        planning
        and int(planning.planned_invoice_count or 0) == EXPECTED_INVOICE_COUNT
        and flt(planning.planned_total_amount or 0, 2) == EXPECTED_TOTAL_AMOUNT
        and int(planning.planned_payment_entry_count or 0) == DESIGN_PAYMENT_ENTRY_COUNT
        and int(planning.planned_gl_entry_count or 0) == DESIGN_GL_ENTRY_COUNT
    )
    planned_side_effects_ok = int(
        planning
        and int(planning.planned_live_posting_allowed or 0) == 0
        and int(planning.planned_journal_entry_side_effect_allowed or 0) == 0
        and int(planning.planned_purchase_invoice_side_effect_allowed or 0) == 0
    )
    items = build_items(rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Design Approved" if completed else "Needs Review",
        "design_status": "Next Governed Limited Operation Design Approved" if completed else "Needs Review",
        "design_approved": completed,
        "phase12n_planning_verified": 1 if planning else 0,
        "planning_approved_verified": 1 if planning else 0,
        "planned_source_verified": planned_source_ok,
        "planned_reference_verified": planned_reference_ok,
        "planned_party_type_verified": planned_party_ok,
        "planned_shape_verified": planned_shape_ok,
        "planned_side_effects_blocked_verified": planned_side_effects_ok,
        "design_source_locked": completed,
        "design_shape_locked": completed,
        "design_reference_set_locked": completed,
        "design_reference_set_verified": int(reference_names(rows) == EXPECTED_INVOICES),
        "candidate_selection_not_started": completed,
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "design_source_doctype": DESIGN_SOURCE_DOCTYPE,
        "design_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
        "design_party_type": DESIGN_PARTY_TYPE,
        "design_customer": unique_value(rows, "customer"),
        "design_company": unique_value(rows, "company"),
        "design_currency": unique_value(rows, "currency"),
        "design_invoice_names": ", ".join(reference_names(rows)),
        "design_invoice_count": len(rows),
        "design_total_amount": design_total(rows),
        "design_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
        "design_gl_entry_count": DESIGN_GL_ENTRY_COUNT,
        "design_live_posting_allowed": 0,
        "design_journal_entry_side_effect_allowed": 0,
        "design_purchase_invoice_side_effect_allowed": 0,
        "ready_for_next_governed_limited_op_candidate_selection_gate": completed,
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
        "target_policy": planning.target_policy if planning else None,
        "target_policy_name": planning.target_policy_name if planning else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        "planning": planning.name if planning else None,
        "monitor": planning.monitor if planning else None,
        "baseline": planning.baseline if planning else None,
        "closeout": planning.closeout if planning else None,
        "freeze": planning.freeze if planning else None,
        "rollback": planning.rollback if planning else None,
        "smoke": planning.smoke if planning else None,
        "execution_gate": planning.execution_gate if planning else None,
        "preview": planning.preview if planning else None,
        "candidate_validation": planning.candidate_validation if planning else None,
        "candidate_selection": planning.candidate_selection if planning else None,
        "previous_design": planning.design if planning else None,
        **item_summary,
        "items": items,
        "issues": post_issues,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12O approves the next governed limited-operation design gate only. No accounting movement occurs.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(DESIGN_DOCTYPE)
    doc.design_id = make_design_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.design_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "design": doc.name, "design_id": doc.design_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_design_audit(design, reason=None):
    assert_action("cancel_next_governed_limited_operation_design_audit")
    if not frappe.db.exists(DESIGN_DOCTYPE, design):
        frappe.throw(_("Next governed limited-operation design audit not found: {0}").format(design))
    doc = frappe.get_doc(DESIGN_DOCTYPE, design)
    if doc.status == "Cancelled":
        return {"design": design, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.design_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 12O design record."))
    frappe.db.set_value(
        DESIGN_DOCTYPE,
        design,
        {
            "status": "Cancelled",
            "design_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12O no-ack design audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{DESIGN_ITEM_DOCTYPE}` SET status='Cancelled' WHERE design=%(design)s", {"design": design})
    frappe.db.commit()
    return {"design": design, "status": "Cancelled", "note": "No-ack design audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_design_summary(limit=20):
    return {
        "design_records": frappe.get_all(
            DESIGN_DOCTYPE,
            fields=[
                "name",
                "design_id",
                "status",
                "design_status",
                "design_approved",
                "design_source_doctype",
                "design_reference_doctype",
                "design_party_type",
                "design_invoice_names",
                "design_invoice_count",
                "design_total_amount",
                "design_payment_entry_count",
                "design_gl_entry_count",
                "design_live_posting_allowed",
                "design_journal_entry_side_effect_allowed",
                "design_purchase_invoice_side_effect_allowed",
                "design_source_locked",
                "design_shape_locked",
                "design_reference_set_locked",
                "design_reference_set_verified",
                "candidate_selection_not_started",
                "ready_for_next_governed_limited_op_candidate_selection_gate",
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
            DESIGN_ITEM_DOCTYPE,
            fields=[
                "name",
                "design",
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
                "design_amount",
                "current_outstanding_amount",
                "monitored_payment_entry",
                "detail",
            ],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12O next governed limited-operation design summary.",
    }


def execute_design_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            name AS design, design_id, status, design_status, design_approved,
            design_source_doctype, design_reference_doctype, design_party_type,
            design_invoice_names, design_invoice_count, design_total_amount,
            design_payment_entry_count, design_gl_entry_count, design_source_locked,
            design_shape_locked, design_reference_set_locked,
            ready_for_next_governed_limited_op_candidate_selection_gate,
            monitored_payment_entry, payment_entry_count_before, payment_entry_count_after,
            payment_entry_gl_count_before, payment_entry_gl_count_after,
            actual_gl_created_count, checked_on, %(currency)s AS currency
        FROM `tab{DESIGN_DOCTYPE}`
        {build_where(conditions)}
        ORDER BY creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "design_id", "label": _("Design ID"), "fieldtype": "Data", "width": 450},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "design_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "design_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "design_invoice_count", "label": _("Invoice Count"), "fieldtype": "Int", "width": 105},
        {"fieldname": "design_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "design_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "design_gl_entry_count", "label": _("Future GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "ready_for_next_governed_limited_op_candidate_selection_gate", "label": _("Candidate Ready"), "fieldtype": "Check", "width": 135},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    chart = {
        "data": {
            "labels": [row.design_id for row in data[:20]],
            "datasets": [
                {"name": "Design Approved", "values": [int(row.design_approved or 0) for row in data[:20]]},
                {"name": "Candidate Ready", "values": [int(row.ready_for_next_governed_limited_op_candidate_selection_gate or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Records"), "datatype": "Int"},
        {"value": sum(int(row.design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    data = frappe.db.sql(
        f"""
        SELECT
            name AS item, design, status, category, line_no, reference_doctype,
            reference_name, design_amount, current_outstanding_amount,
            monitored_payment_entry, check_label, detail
        FROM `tab{DESIGN_ITEM_DOCTYPE}`
        ORDER BY creation DESC
        """,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": DESIGN_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "design_amount", "label": _("Design Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "current_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
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
        {"value": len([row for row in data if row.category == "Designed Reference"]), "indicator": "Green", "label": _("Designed References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_design_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
