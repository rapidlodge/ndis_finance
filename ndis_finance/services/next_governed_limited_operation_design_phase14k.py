import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE14K_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_DESIGN_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"
DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"

PLANNING_READY_FIELD = "ready_for_next_governed_limited_op_design"
DESIGN_READY_FIELD = "ready_for_next_governed_limited_op_candidate_selection"

GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00015"
PREVIOUS_GATED_PAYMENT_ENTRY = "ACC-PAY-2026-00014"
DESIGN_PAYMENT_ENTRY = "ACC-PAY-2026-00016"
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]
EXPECTED_PAYMENT_ENTRY_COUNT = 15
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 102
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_INVOICE_COUNT = 3
EXPECTED_GL_ROWS = 8
EXPECTED_REVERSAL_GL_ROWS = 4
EXPECTED_GL_NET = 0.00

DESIGN_SOURCE_DOCTYPE = "Sales Invoice"
DESIGN_REFERENCE_DOCTYPE = "Sales Invoice"
DESIGN_PARTY_TYPE = "Customer"


def make_design_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_phase14j_planning():
    filters = {
        "status": "Planning Approved",
        "planning_status": "Next Governed Limited Operation Planning Approved",
        "planning_approved": 1,
        "phase14i_monitor_verified": 1,
        "monitor_active_verified": 1,
        "monitor_payment_entry_verified": 1,
        "monitor_payment_entry_cancelled_verified": 1,
        "monitor_gl_rows_verified": 1,
        "monitor_reversal_gl_rows_verified": 1,
        "monitor_gl_net_zero_verified": 1,
        "monitor_restored_invoice_amount_verified": 1,
        "policy_state_preserved_verified": 1,
        "no_new_accounting_movement_verified": 1,
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": 2,
        "gated_payment_entry_status": "Cancelled",
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": 2,
        "previous_gated_payment_entry_status": "Cancelled",
        "planning_payment_entry": DESIGN_PAYMENT_ENTRY,
        "planning_payment_entry_docstatus": 2,
        "planning_payment_entry_status": "Cancelled",
        "planning_source_doctype": DESIGN_SOURCE_DOCTYPE,
        "planning_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
        "planning_party_type": DESIGN_PARTY_TYPE,
        "planning_invoice_count": EXPECTED_INVOICE_COUNT,
        "planning_total_amount": EXPECTED_TOTAL_AMOUNT,
        "planning_restored_invoice_amount": EXPECTED_TOTAL_AMOUNT,
        "planning_gl_rows": EXPECTED_GL_ROWS,
        "planning_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "planning_gl_net": EXPECTED_GL_NET,
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
    if has_column(PLANNING_DOCTYPE, PLANNING_READY_FIELD):
        filters[PLANNING_READY_FIELD] = 1

    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "planning_id",
            "gated_payment_entry",
            "gated_payment_entry_docstatus",
            "gated_payment_entry_status",
            "previous_gated_payment_entry",
            "previous_gated_payment_entry_docstatus",
            "previous_gated_payment_entry_status",
            "planning_payment_entry",
            "planning_source_doctype",
            "planning_reference_doctype",
            "planning_party_type",
            "planning_customer",
            "planning_company",
            "planning_currency",
            "planning_invoice_names",
            "planning_invoice_count",
            "planning_total_amount",
            "planning_restored_invoice_amount",
            "planning_gl_rows",
            "planning_reversal_gl_rows",
            "planning_gl_net",
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
        fields=["name", "design_id", "design_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def planning_rows(planning):
    rows = frappe.get_all(
        PLANNING_ITEM_DOCTYPE,
        filters={"planning": planning, "category": "Planning Reference", "status": "Pass", "reference_doctype": "Sales Invoice"},
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "planning_amount",
            "outstanding_amount",
            "planning_payment_entry",
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
                    "design_amount": flt(row.planning_amount or 0, 2),
                    "outstanding_amount": flt((si.outstanding_amount if si else row.outstanding_amount) or 0, 2),
                    "customer": si.customer if si else row.customer,
                    "company": si.company if si else row.company,
                    "currency": si.currency if si else row.currency,
                    "invoice_docstatus": int(si.docstatus or 0) if si else 0,
                    "design_payment_entry": DESIGN_PAYMENT_ENTRY,
                    "gated_payment_entry": GATED_PAYMENT_ENTRY,
                }
            )
        )
    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def design_total(rows):
    return flt(sum(flt(row.design_amount or 0, 2) for row in rows), 2)


def unique_value(rows, fieldname):
    values = sorted(set([getattr(row, fieldname, None) for row in rows if getattr(row, fieldname, None)]))
    return values[0] if len(values) == 1 else None


def validate_source(planning, rows, guard, config, policy_enabled, policy_live):
    issues = []
    if not planning:
        issues.append("No approved Phase 14J planning found for design.")
        return issues

    existing = existing_approved_design(planning.name)
    if existing:
        issues.append(f"Approved Phase 14K design already exists for this planning: {existing.design_id} / {existing.design_payment_entry}")

    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    state = payment_entry_state(DESIGN_PAYMENT_ENTRY)
    if not frappe.db.exists("Payment Entry", GATED_PAYMENT_ENTRY):
        issues.append(f"Gated Payment Entry does not exist: {GATED_PAYMENT_ENTRY}")
    if gated_state.docstatus != 2 or gated_state.status != "Cancelled":
        issues.append(f"Gated Payment Entry must remain Cancelled / 2. Found {gated_state.status} / {gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", PREVIOUS_GATED_PAYMENT_ENTRY):
        issues.append(f"Previous gated Payment Entry does not exist: {PREVIOUS_GATED_PAYMENT_ENTRY}")
    if previous_gated_state.docstatus != 2 or previous_gated_state.status != "Cancelled":
        issues.append(f"Previous gated Payment Entry must remain Cancelled / 2. Found {previous_gated_state.status} / {previous_gated_state.docstatus}")
    if not frappe.db.exists("Payment Entry", DESIGN_PAYMENT_ENTRY):
        issues.append(f"Design Payment Entry does not exist: {DESIGN_PAYMENT_ENTRY}")
    if state.docstatus != 2 or state.status != "Cancelled":
        issues.append(f"Design Payment Entry must remain Cancelled / 2. Found {state.status} / {state.docstatus}")
    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Design invoice set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")
    if len(rows) != EXPECTED_INVOICE_COUNT:
        issues.append(f"Design invoice count must be {EXPECTED_INVOICE_COUNT}. Found {len(rows)}.")
    if design_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Design total amount must be {EXPECTED_TOTAL_AMOUNT}. Found {design_total(rows)}.")
    if outstanding_total(EXPECTED_INVOICES) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Restored invoice outstanding must be {EXPECTED_TOTAL_AMOUNT} before design.")
    if payment_entry_gl_rows(DESIGN_PAYMENT_ENTRY) != EXPECTED_GL_ROWS:
        issues.append(f"Design Payment Entry must have {EXPECTED_GL_ROWS} GL rows.")
    if payment_entry_gl_net(DESIGN_PAYMENT_ENTRY) != EXPECTED_GL_NET:
        issues.append("Design Payment Entry GL net must be 0.00.")
    if int(planning.planning_reversal_gl_rows or 0) != EXPECTED_REVERSAL_GL_ROWS:
        issues.append("Governed planning reversal rows must remain the four-row delta.")
    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 15 before design.")
    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 102 before design.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must remain 0 before design.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must remain 0 before design.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled before design.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0 before design.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")
    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled for design.")
    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0 for design.")
    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0 for design.")
    return issues


def build_items(rows, issues, ack_ok):
    items = []
    if not issues:
        items.append({
            "status": "Pass",
            "severity": "Critical",
            "category": "Design Source",
            "check_key": "design_source_valid",
            "check_label": "Design source valid",
            "detail": f"Phase 14J planning evidence for {DESIGN_PAYMENT_ENTRY} is stable and ready for design approval.",
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "design_payment_entry": DESIGN_PAYMENT_ENTRY,
        })
    else:
        for issue in issues:
            items.append({
                "status": "Blocker",
                "severity": "Critical",
                "category": "Design Source",
                "check_key": "design_source_valid",
                "check_label": "Design source valid",
                "detail": issue,
                "gated_payment_entry": GATED_PAYMENT_ENTRY,
                "design_payment_entry": DESIGN_PAYMENT_ENTRY,
            })

    for row in rows:
        items.append({
            "status": "Pass",
            "severity": "High",
            "category": "Design Reference",
            "check_key": "design_sales_invoice_reference",
            "check_label": f"Design Sales Invoice {row.idx}",
            "detail": f"{row.reference_name} design amount={row.design_amount}, outstanding={row.outstanding_amount}.",
            "line_no": row.idx,
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_name,
            "customer": row.customer,
            "company": row.company,
            "currency": row.currency,
            "design_amount": row.design_amount,
            "outstanding_amount": row.outstanding_amount,
            "gated_payment_entry": GATED_PAYMENT_ENTRY,
            "design_payment_entry": DESIGN_PAYMENT_ENTRY,
        })

    items.append({
        "status": "Pass" if ack_ok else "Warning",
        "severity": "Low" if ack_ok else "Medium",
        "category": "Acknowledgement",
        "check_key": "ack_ok",
        "check_label": "Acknowledgement supplied",
        "detail": "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {DESIGN_ACK}",
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "design_payment_entry": DESIGN_PAYMENT_ENTRY,
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
        row = frappe.new_doc(DESIGN_ITEM_DOCTYPE)
        row.design = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_design_phase14k(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_design_phase14k")

    planning = latest_phase14j_planning()
    rows = planning_rows(planning.name) if planning else []
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
    gated_state = payment_entry_state(GATED_PAYMENT_ENTRY)
    previous_gated_state = payment_entry_state(PREVIOUS_GATED_PAYMENT_ENTRY)
    state = payment_entry_state(DESIGN_PAYMENT_ENTRY)
    design_gl_rows = payment_entry_gl_rows(DESIGN_PAYMENT_ENTRY)
    design_gl_net = payment_entry_gl_net(DESIGN_PAYMENT_ENTRY)
    restored_amount = outstanding_total(EXPECTED_INVOICES)
    direct_cancelled_rows = direct_cancelled_gl_rows(DESIGN_PAYMENT_ENTRY)
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
        post_issues.append(f"Design must create 0 Payment Entries. Created {actual_pe_created}.")
    if actual_pe_cancelled != 0:
        post_issues.append(f"Design must cancel 0 Payment Entries. Cancelled {actual_pe_cancelled}.")
    if actual_gl_created != 0:
        post_issues.append(f"Design must create 0 GL rows. Created {actual_gl_created}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry today must remain 0 after design.")
    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice today must remain 0 after design.")
    if policy_mutation_count != 0:
        post_issues.append("Policy state changed during design. This is not allowed.")

    completed = int(
        not int(dry_run or 0)
        and ack_ok
        and planning
        and not post_issues
        and gated_state.docstatus == 2
        and gated_state.status == "Cancelled"
        and previous_gated_state.docstatus == 2
        and previous_gated_state.status == "Cancelled"
        and state.docstatus == 2
        and state.status == "Cancelled"
        and design_gl_rows == EXPECTED_GL_ROWS
        and design_gl_net == EXPECTED_GL_NET
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
        "status": "Design Approved" if completed else "Needs Review",
        "design_status": "Next Governed Limited Operation Design Approved" if completed else "Needs Review",
        "design_approved": completed,
        "phase14j_planning_verified": 1 if planning else 0,
        "planning_approved_verified": 1 if planning else 0,
        "planning_payment_entry_verified": int(planning and planning.planning_payment_entry == DESIGN_PAYMENT_ENTRY),
        "planning_payment_entry_cancelled_verified": int(state.docstatus == 2 and state.status == "Cancelled"),
        "planning_gl_rows_verified": int(design_gl_rows == EXPECTED_GL_ROWS),
        "planning_reversal_gl_rows_verified": int(planning and int(planning.planning_reversal_gl_rows or 0) == EXPECTED_REVERSAL_GL_ROWS),
        "planning_gl_net_zero_verified": int(design_gl_net == EXPECTED_GL_NET),
        "planning_restored_invoice_amount_verified": int(restored_amount == EXPECTED_TOTAL_AMOUNT),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "gated_payment_entry": GATED_PAYMENT_ENTRY,
        "gated_payment_entry_docstatus": gated_state.docstatus,
        "gated_payment_entry_status": gated_state.status,
        "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY,
        "previous_gated_payment_entry_docstatus": previous_gated_state.docstatus,
        "previous_gated_payment_entry_status": previous_gated_state.status,
        "design_payment_entry": DESIGN_PAYMENT_ENTRY,
        "design_payment_entry_docstatus": state.docstatus,
        "design_payment_entry_status": state.status,
        "design_source_doctype": DESIGN_SOURCE_DOCTYPE,
        "design_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
        "design_party_type": DESIGN_PARTY_TYPE,
        "design_customer": unique_value(rows, "customer"),
        "design_company": unique_value(rows, "company"),
        "design_currency": unique_value(rows, "currency"),
        "design_invoice_names": ", ".join(reference_names(rows)),
        "design_invoice_count": len(rows),
        "design_total_amount": design_total(rows),
        "design_restored_invoice_amount": restored_amount,
        "design_gl_rows": design_gl_rows,
        "design_reversal_gl_rows": EXPECTED_REVERSAL_GL_ROWS,
        "design_gl_net": design_gl_net,
        "design_direct_cancelled_gl_rows": direct_cancelled_rows,
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
        "target_policy": planning.target_policy if planning else None,
        "target_policy_name": planning.target_policy_name if planning else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "actual_policy_mutation_count": policy_mutation_count,
        DESIGN_READY_FIELD: completed,
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
        "note": "Phase 14K approves next governed limited-operation design. No accounting movement occurs.",
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
    return {**result, "created": True, "design": doc.name, "design_id": doc.design_id, "gated_payment_entry": GATED_PAYMENT_ENTRY, "previous_gated_payment_entry": PREVIOUS_GATED_PAYMENT_ENTRY, "design_payment_entry": DESIGN_PAYMENT_ENTRY, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_next_governed_limited_operation_design_phase14k_audit(design, reason=None):
    assert_action("cancel_next_governed_limited_operation_design_phase14k_audit")
    if not frappe.db.exists(DESIGN_DOCTYPE, design):
        frappe.throw(_("Next governed limited-operation design audit not found: {0}").format(design))
    doc = frappe.get_doc(DESIGN_DOCTYPE, design)
    if doc.status == "Cancelled":
        return {"design": design, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.design_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 14K design record."))
    frappe.db.set_value(
        DESIGN_DOCTYPE,
        design,
        {"status": "Cancelled", "design_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 14K no-ack design audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{DESIGN_ITEM_DOCTYPE}` SET status='Cancelled' WHERE design=%(design)s", {"design": design})
    frappe.db.commit()
    return {"design": design, "status": "Cancelled", "note": "No-ack design audit cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_next_governed_limited_operation_design_phase14k_summary(limit=20):
    return {
        "design_records": frappe.get_all(
            DESIGN_DOCTYPE,
            filters={"design_payment_entry": DESIGN_PAYMENT_ENTRY},
            fields=["name", "design_id", "status", "design_status", "design_approved", "design_payment_entry", "design_payment_entry_docstatus", "design_payment_entry_status", "design_invoice_names", "design_invoice_count", "design_total_amount", "design_restored_invoice_amount", "design_gl_rows", "design_reversal_gl_rows", "design_gl_net", "payment_entry_count_before", "payment_entry_count_after", "payment_entry_gl_count_before", "payment_entry_gl_count_after", "actual_payment_entry_created_count", "actual_payment_entry_cancelled_count", "actual_gl_created_count", "submitted_journal_entry_count_today", "purchase_invoice_count_today", DESIGN_READY_FIELD, "checked_on", "checked_by"],
            order_by="creation desc",
            limit=int(limit or 20),
        ),
        "items": frappe.db.sql(
            f"""
            SELECT
                i.name,
                i.design,
                i.status,
                i.severity,
                i.category,
                i.check_key,
                i.check_label,
                i.line_no,
                i.reference_doctype,
                i.reference_name,
                i.customer,
                i.company,
                i.currency,
                i.design_amount,
                i.outstanding_amount,
                i.gated_payment_entry,
                i.design_payment_entry,
                i.detail
            FROM `tab{DESIGN_ITEM_DOCTYPE}` i
            INNER JOIN `tab{DESIGN_DOCTYPE}` d ON d.name = i.design
            WHERE d.design_payment_entry = %(payment_entry)s
            ORDER BY i.creation DESC
            LIMIT %(limit)s
            """,
            {"payment_entry": DESIGN_PAYMENT_ENTRY, "limit": int(limit or 20)},
            as_dict=True,
        ),
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "note": "Phase 14K next governed limited-operation design summary.",
    }


def execute_design_phase14k_report(filters=None):
    columns = [
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "design_id", "label": _("Design ID"), "fieldtype": "Data", "width": 540},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 390},
        {"fieldname": "design_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "design_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "design_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_invoice_names", "label": _("Invoices"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "design_total_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "design_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "design_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 90},
        {"fieldname": "design_reversal_gl_rows", "label": _("Reversal Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "design_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "width": 100},
        {"fieldname": DESIGN_READY_FIELD, "label": _("Candidate Selection Ready"), "fieldtype": "Check", "width": 180},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 115},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 115},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 135},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT name AS design, design_id, status, design_status, design_approved,
            gated_payment_entry, design_payment_entry, design_payment_entry_status, design_invoice_names,
            design_total_amount, design_restored_invoice_amount, design_gl_rows,
            design_reversal_gl_rows, design_gl_net,
            `{DESIGN_READY_FIELD}` AS `{DESIGN_READY_FIELD}`,
            payment_entry_count_before, payment_entry_count_after,
            payment_entry_gl_count_before, payment_entry_gl_count_after,
            actual_gl_created_count, checked_on
        FROM `tab{DESIGN_DOCTYPE}`
        WHERE design_payment_entry=%(payment_entry)s
        ORDER BY creation DESC
        """,
        {"payment_entry": DESIGN_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {"data": {"labels": [row.design_id for row in data[:20]], "datasets": [{"name": "Design Approved", "values": [int(row.design_approved or 0) for row in data[:20]]}, {"name": "Candidate Selection Ready", "values": [int(row.get(DESIGN_READY_FIELD) or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Records"), "datatype": "Int"},
        {"value": sum(int(row.design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_item_report(filters=None):
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": DESIGN_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "design_amount", "label": _("Design Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "gated_payment_entry", "label": _("Gated PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "design_payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.design,
            i.status,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.design_amount,
            i.outstanding_amount,
            i.gated_payment_entry,
            i.design_payment_entry,
            i.detail
        FROM `tab{DESIGN_ITEM_DOCTYPE}` i
        INNER JOIN `tab{DESIGN_DOCTYPE}` d ON d.name = i.design
        WHERE d.design_payment_entry=%(payment_entry)s
        ORDER BY i.creation DESC
        """,
        {"payment_entry": DESIGN_PAYMENT_ENTRY},
        as_dict=True,
    )
    chart = {"data": {"labels": ["Pass", "Warning", "Blocker", "Info"], "datasets": [{"name": "Items", "values": [len([row for row in data if row.status == "Pass"]), len([row for row in data if row.status == "Warning"]), len([row for row in data if row.status == "Blocker"]), len([row for row in data if row.status == "Info"])]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Design Reference"]), "indicator": "Green", "label": _("Design References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_design_phase14k_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary
