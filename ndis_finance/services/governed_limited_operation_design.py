import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE12C_APPROVE_GOVERNED_LIMITED_OPERATION_DESIGN_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PLANNING_DOCTYPE = "NDIS Next Governed Limited Op Planning"
PLANNING_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Planning Item"
DESIGN_DOCTYPE = "NDIS Next Governed Limited Op Design"
DESIGN_ITEM_DOCTYPE = "NDIS Next Governed Limited Op Design Item"

EXPECTED_PAYMENT_ENTRY = "ACC-PAY-2026-00011"
EXPECTED_REFERENCE_COUNT = 3
EXPECTED_TOTAL_AMOUNT = 3.00
EXPECTED_VOUCHER_GL_ROWS = 8
EXPECTED_PAYMENT_ENTRY_COUNT = 10
EXPECTED_PAYMENT_ENTRY_GL_COUNT = 62
EXPECTED_INVOICES = ["ACC-SINV-2026-00005", "ACC-SINV-2026-00006", "ACC-SINV-2026-00008"]

DESIGN_SOURCE_DOCTYPE = "Sales Invoice"
DESIGN_REFERENCE_DOCTYPE = "Sales Invoice"
DESIGN_PARTY_TYPE = "Customer"
DESIGN_LINE_COUNT = 3
DESIGN_TOTAL_AMOUNT = 3.00
DESIGN_PAYMENT_ENTRY_COUNT = 1


def make_design_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-NEXT-GOVERNED-LIMITED-OP-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_planning():
    rows = frappe.get_all(
        PLANNING_DOCTYPE,
        filters={
            "status": "Planning Approved",
            "planning_status": "Governed Limited Operation Planning Approved",
            "planning_approved": 1,
            "phase12a_monitor_verified": 1,
            "monitor_active_verified": 1,
            "baseline_active_verified": 1,
            "planning_envelope_locked": 1,
            "planning_source_locked": 1,
            "planning_shape_locked": 1,
            "candidate_selection_not_started": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "ready_for_governed_limited_operation_design_gate": 1,
            "planned_source_doctype": DESIGN_SOURCE_DOCTYPE,
            "planned_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
            "planned_party_type": DESIGN_PARTY_TYPE,
            "planned_line_count": DESIGN_LINE_COUNT,
            "planned_total_amount": DESIGN_TOTAL_AMOUNT,
            "planned_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
            "planned_live_posting_allowed": 0,
            "planned_journal_entry_side_effect_allowed": 0,
            "planned_purchase_invoice_side_effect_allowed": 0,
            "monitored_payment_entry": EXPECTED_PAYMENT_ENTRY,
            "payment_entry_docstatus_planning": 2,
            "payment_entry_status_planning": "Cancelled",
            "monitored_reference_count": EXPECTED_REFERENCE_COUNT,
            "monitored_total_amount": EXPECTED_TOTAL_AMOUNT,
            "monitored_voucher_gl_rows": EXPECTED_VOUCHER_GL_ROWS,
            "monitored_voucher_gl_net": 0.00,
            "monitored_voucher_gl_non_zero_account_count": 0,
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
        },
        fields=[
            "name",
            "planning_id",
            "monitored_payment_entry",
            "planned_source_doctype",
            "planned_reference_doctype",
            "planned_party_type",
            "planned_line_count",
            "planned_total_amount",
            "planned_payment_entry_count",
            "planned_live_posting_allowed",
            "planned_journal_entry_side_effect_allowed",
            "planned_purchase_invoice_side_effect_allowed",
            "monitor",
            "baseline",
            "closeout",
            "freeze",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "validation",
            "candidate",
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
        filters={
            "planning": planning,
            "status": "Design Approved",
            "design_approved": 1,
        },
        fields=["name", "design_id", "monitored_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def planning_rows(planning):
    if not planning:
        return []

    rows = frappe.get_all(
        PLANNING_ITEM_DOCTYPE,
        filters={
            "planning": planning,
            "category": "Planning Envelope Reference",
            "status": "Pass",
            "reference_doctype": "Sales Invoice",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "allocated_amount",
            "current_outstanding_amount",
            "monitored_payment_entry",
        ],
        order_by="line_no asc, creation asc",
    )

    result = []
    for idx, row in enumerate(rows, start=1):
        outstanding = frappe.db.get_value("Sales Invoice", row.reference_name, "outstanding_amount")
        result.append(
            frappe._dict(
                {
                    "idx": int(row.line_no or idx),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "allocated_amount": flt(row.allocated_amount or 0, 2),
                    "current_outstanding_amount": flt(outstanding or row.current_outstanding_amount or 0, 2),
                    "monitored_payment_entry": row.monitored_payment_entry,
                }
            )
        )

    return result


def reference_names(rows):
    return [row.reference_name for row in rows]


def allocated_total(rows):
    return flt(sum(flt(row.allocated_amount or 0, 2) for row in rows), 2)


def current_outstanding_total(rows):
    return flt(sum(flt(row.current_outstanding_amount or 0, 2) for row in rows), 2)


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


def validate_source(planning, payment_entry, rows, guard, config, policy_enabled, policy_live):
    issues = []

    if not planning:
        issues.append("No approved Phase 12B governed limited-operation planning found.")
        return issues

    existing = existing_approved_design(planning.name)
    if existing:
        issues.append(f"Approved Phase 12C design already exists for this planning: {existing.design_id} / {existing.monitored_payment_entry}")

    if planning.planned_source_doctype != DESIGN_SOURCE_DOCTYPE:
        issues.append(f"Planned source doctype must be {DESIGN_SOURCE_DOCTYPE}. Found {planning.planned_source_doctype}.")

    if planning.planned_reference_doctype != DESIGN_REFERENCE_DOCTYPE:
        issues.append(f"Planned reference doctype must be {DESIGN_REFERENCE_DOCTYPE}. Found {planning.planned_reference_doctype}.")

    if planning.planned_party_type != DESIGN_PARTY_TYPE:
        issues.append(f"Planned party type must be {DESIGN_PARTY_TYPE}. Found {planning.planned_party_type}.")

    if int(planning.planned_line_count or 0) != DESIGN_LINE_COUNT:
        issues.append(f"Planned line count must be {DESIGN_LINE_COUNT}. Found {planning.planned_line_count}.")

    if flt(planning.planned_total_amount or 0, 2) != DESIGN_TOTAL_AMOUNT:
        issues.append(f"Planned total amount must be {DESIGN_TOTAL_AMOUNT}. Found {planning.planned_total_amount}.")

    if int(planning.planned_payment_entry_count or 0) != DESIGN_PAYMENT_ENTRY_COUNT:
        issues.append(f"Planned Payment Entry count must be {DESIGN_PAYMENT_ENTRY_COUNT}. Found {planning.planned_payment_entry_count}.")

    if int(planning.planned_live_posting_allowed or 0) != 0:
        issues.append("Planned live posting must remain disabled.")

    if int(planning.planned_journal_entry_side_effect_allowed or 0) != 0:
        issues.append("Planned Journal Entry side effects must remain disabled.")

    if int(planning.planned_purchase_invoice_side_effect_allowed or 0) != 0:
        issues.append("Planned Purchase Invoice side effects must remain disabled.")

    if not payment_entry:
        issues.append("Phase 12B planning did not identify a monitored Payment Entry.")
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

    if reference_names(rows) != EXPECTED_INVOICES:
        issues.append(f"Design reference set changed. Expected {EXPECTED_INVOICES}. Found {reference_names(rows)}.")

    if allocated_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Design allocated total must be {EXPECTED_TOTAL_AMOUNT}. Found {allocated_total(rows)}.")

    if current_outstanding_total(rows) != EXPECTED_TOTAL_AMOUNT:
        issues.append(f"Design restored outstanding total must be {EXPECTED_TOTAL_AMOUNT}. Found {current_outstanding_total(rows)}.")

    if guard["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        issues.append("Payment Entry count must remain 10 before Phase 12C design.")

    if guard["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        issues.append("Payment Entry GL count must remain 62 before Phase 12C design.")

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
                "allocated_amount": row.allocated_amount,
                "current_outstanding_amount": row.current_outstanding_amount,
            }
        )

    items.append(item)


def build_items(planning, rows, issues, ack_ok, payment_entry=None):
    items = []

    if planning:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase12b_planning_exists",
            "Phase 12B planning exists",
            f"Planning found: {planning.planning_id}.",
            payment_entry=payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase12b_planning_exists", "Phase 12B planning exists", "No approved Phase 12B planning found.")

    if not issues:
        add_item(
            items,
            "Pass",
            "Critical",
            "Design Source",
            "design_source_valid",
            "Design source valid",
            "The approved planning envelope can be locked as the governed limited-operation design.",
            payment_entry=payment_entry,
        )
    else:
        for issue in issues:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Design Source",
                "design_source_valid",
                "Design source valid",
                issue,
                payment_entry=payment_entry,
            )

    for row in rows:
        add_item(
            items,
            "Pass",
            "High",
            "Design Envelope Reference",
            "design_sales_invoice_reference",
            f"Design Sales Invoice {row.idx}",
            f"{row.reference_name} designed with allocated={row.allocated_amount}, outstanding={row.current_outstanding_amount}.",
            row=row,
            payment_entry=payment_entry,
        )

    checks = [
        ("design_envelope", "Design envelope locked", f"{DESIGN_LINE_COUNT} / {DESIGN_TOTAL_AMOUNT} / {DESIGN_PAYMENT_ENTRY_COUNT}"),
        ("source_lock", "Source/reference/party locked", f"{DESIGN_SOURCE_DOCTYPE} / {DESIGN_REFERENCE_DOCTYPE} / {DESIGN_PARTY_TYPE}"),
        ("candidate_not_started", "Candidate selection not started", 1),
        ("live_posting_disabled", "Live posting not allowed", 0),
        ("je_side_effect_disabled", "Journal Entry side effect not allowed", 0),
        ("pi_side_effect_disabled", "Purchase Invoice side effect not allowed", 0),
        ("payment_entry_cancelled_still", "Payment Entry remains Cancelled", payment_entry or "None"),
        ("payment_entry_count", "Payment Entry count remains 10", "10 -> 10"),
        ("payment_entry_gl_count", "Payment Entry GL count remains 62", "62 -> 62"),
        ("voucher_gl_rows", "Voucher GL rows remain 8", EXPECTED_VOUCHER_GL_ROWS),
        ("voucher_gl_net", "Voucher GL net remains 0.00", 0),
        ("invoice_restored", "Invoice outstanding remains restored = 3.00", EXPECTED_TOTAL_AMOUNT),
        ("no_pe_movement", "No Payment Entry movement", "0 / 0"),
        ("no_gl_movement", "No GL movement", 0),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("candidate_selection_ready", "Ready for governed limited-operation candidate selection gate", 1),
    ]

    for key, label, value in checks:
        add_item(
            items,
            "Pass",
            "High",
            "Design Evidence",
            key,
            label,
            f"value={value}",
            payment_entry=payment_entry,
        )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", payment_entry=payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {DESIGN_ACK}")

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
        row = frappe.new_doc(DESIGN_ITEM_DOCTYPE)
        row.design = doc.name
        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_design(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_design")

    planning = latest_planning()
    payment_entry = planning.monitored_payment_entry if planning else None
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

    source_issues = validate_source(planning, payment_entry, rows, guard_before, config, policy_enabled_before, policy_live_before)

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
    reference_count = 0
    total_amount = 0
    voucher_rows = 0
    voucher_net = 0
    voucher_non_zero_accounts = 0
    restored_invoice_amount = current_outstanding_total(rows)

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
        post_issues.append(f"Design must not create Payment Entries. Created {actual_pe_created}.")

    if actual_pe_cancelled != 0:
        post_issues.append(f"Design must not cancel Payment Entries. Cancelled {actual_pe_cancelled}.")

    if actual_gl_created != 0:
        post_issues.append(f"Design must not create GL rows. Created {actual_gl_created}.")

    if guard_after["payment_entry_count"] != EXPECTED_PAYMENT_ENTRY_COUNT:
        post_issues.append("Payment Entry count must remain 10 after design.")

    if guard_after["payment_entry_gl_count"] != EXPECTED_PAYMENT_ENTRY_GL_COUNT:
        post_issues.append("Payment Entry GL count must remain 62 after design.")

    if guard_after["submitted_journal_entry_count_today"] != 0:
        post_issues.append("Submitted Journal Entry count today must remain 0 after design.")

    if guard_after["purchase_invoice_count_today"] != 0:
        post_issues.append("Purchase Invoice count today must remain 0 after design.")

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
        and reference_count == EXPECTED_REFERENCE_COUNT
        and total_amount == EXPECTED_TOTAL_AMOUNT
        and voucher_rows == EXPECTED_VOUCHER_GL_ROWS
        and voucher_net == 0
        and voucher_non_zero_accounts == 0
        and restored_invoice_amount == EXPECTED_TOTAL_AMOUNT
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

    items = build_items(planning, rows, post_issues, ack_ok, payment_entry=payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Design Approved" if completed else "Needs Review",
        "design_status": "Governed Limited Operation Design Approved" if completed else "Needs Review",
        "design_approved": completed,
        "phase12b_planning_verified": 1 if planning else 0,
        "planning_approved_verified": 1 if planning else 0,
        "planning_envelope_locked_verified": 1 if planning else 0,
        "planning_source_locked_verified": 1 if planning else 0,
        "planning_shape_locked_verified": 1 if planning else 0,
        "candidate_selection_not_started_verified": 1 if planning else 0,
        "design_source_locked": completed,
        "design_shape_locked": completed,
        "candidate_selection_not_started": completed,
        "live_posting_not_allowed_verified": int(planning and int(planning.planned_live_posting_allowed or 0) == 0),
        "journal_entry_side_effect_not_allowed_verified": int(planning and int(planning.planned_journal_entry_side_effect_allowed or 0) == 0),
        "purchase_invoice_side_effect_not_allowed_verified": int(planning and int(planning.planned_purchase_invoice_side_effect_allowed or 0) == 0),
        "monitored_payment_entry_verified": int(bool(payment_entry)),
        "payment_entry_cancelled_still_verified": int(pe_docstatus == 2 and pe_status == "Cancelled"),
        "voucher_gl_rows_verified": int(voucher_rows == EXPECTED_VOUCHER_GL_ROWS),
        "voucher_gl_net_zero_verified": int(voucher_net == 0),
        "invoice_outstanding_restored_still_verified": int(restored_invoice_amount == EXPECTED_TOTAL_AMOUNT),
        "no_new_accounting_movement_verified": int(actual_pe_created == 0 and actual_pe_cancelled == 0 and actual_gl_created == 0),
        "policy_state_preserved_verified": int(policy_mutation_count == 0 and policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0),
        "ready_for_governed_limited_operation_candidate_selection_gate": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,

        "design_source_doctype": DESIGN_SOURCE_DOCTYPE,
        "design_reference_doctype": DESIGN_REFERENCE_DOCTYPE,
        "design_party_type": DESIGN_PARTY_TYPE,
        "design_line_count": DESIGN_LINE_COUNT,
        "design_total_amount": DESIGN_TOTAL_AMOUNT,
        "design_payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
        "design_live_posting_allowed": 0,
        "design_journal_entry_side_effect_allowed": 0,
        "design_purchase_invoice_side_effect_allowed": 0,

        "planned_source_doctype": planning.planned_source_doctype if planning else None,
        "planned_reference_doctype": planning.planned_reference_doctype if planning else None,
        "planned_party_type": planning.planned_party_type if planning else None,
        "planned_line_count": int(planning.planned_line_count or 0) if planning else 0,
        "planned_total_amount": flt(planning.planned_total_amount or 0, 2) if planning else 0,
        "planned_payment_entry_count": int(planning.planned_payment_entry_count or 0) if planning else 0,
        "planned_live_posting_allowed": int(planning.planned_live_posting_allowed or 0) if planning else 0,
        "planned_journal_entry_side_effect_allowed": int(planning.planned_journal_entry_side_effect_allowed or 0) if planning else 0,
        "planned_purchase_invoice_side_effect_allowed": int(planning.planned_purchase_invoice_side_effect_allowed or 0) if planning else 0,

        "monitored_payment_entry": payment_entry,
        "payment_entry_docstatus_design": pe_docstatus,
        "payment_entry_status_design": pe_status,
        "monitored_reference_count": reference_count,
        "monitored_total_amount": total_amount,
        "monitored_voucher_gl_rows": voucher_rows,
        "monitored_voucher_gl_net": voucher_net,
        "monitored_voucher_gl_non_zero_account_count": voucher_non_zero_accounts,
        "monitored_restored_invoice_amount": restored_invoice_amount,

        "planning": planning.name if planning else None,
        "monitor": planning.monitor if planning else None,
        "baseline": planning.baseline if planning else None,
        "closeout": planning.closeout if planning else None,
        "freeze": planning.freeze if planning else None,
        "rollback": planning.rollback if planning else None,
        "smoke": planning.smoke if planning else None,
        "execution_gate": planning.execution_gate if planning else None,
        "preview": planning.preview if planning else None,
        "validation": planning.validation if planning else None,
        "candidate": planning.candidate if planning else None,
        "previous_design": planning.design if planning else None,

        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": planning.target_policy if planning else None,
        "target_policy_name": planning.target_policy_name if planning else None,
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
        "design_score": score,
        **item_summary,
        "items": items,
        "design_references": [dict(row) for row in rows],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 12C locks the governed limited-operation design only. No candidate selection, posting, accounting, or policy movement occurs.",
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
    doc.design_json = safe_json(
        {
            "planning": planning,
            "monitored_payment_entry": payment_entry,
            "design_envelope": {
                "source_doctype": DESIGN_SOURCE_DOCTYPE,
                "reference_doctype": DESIGN_REFERENCE_DOCTYPE,
                "party_type": DESIGN_PARTY_TYPE,
                "line_count": DESIGN_LINE_COUNT,
                "total_amount": DESIGN_TOTAL_AMOUNT,
                "payment_entry_count": DESIGN_PAYMENT_ENTRY_COUNT,
                "live_posting_allowed": 0,
                "journal_entry_side_effect_allowed": 0,
                "purchase_invoice_side_effect_allowed": 0,
            },
            "design_references": [dict(row) for row in rows],
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
        "design": doc.name,
        "design_id": doc.design_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_governed_limited_operation_design_audit(design, reason=None):
    assert_action("cancel_governed_limited_operation_design_audit")

    if not frappe.db.exists(DESIGN_DOCTYPE, design):
        frappe.throw(_("Governed limited-operation design audit not found: {0}").format(design))

    doc = frappe.get_doc(DESIGN_DOCTYPE, design)

    if doc.status == "Cancelled":
        return {"design": design, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.design_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 12C design record."))

    frappe.db.set_value(
        DESIGN_DOCTYPE,
        design,
        {
            "status": "Cancelled",
            "design_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 12C no-ack design audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{DESIGN_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE design = %(design)s
        """,
        {"design": design},
    )

    frappe.db.commit()

    return {
        "design": design,
        "status": "Cancelled",
        "note": "No-ack design audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_governed_limited_operation_design_summary(limit=20):
    records = frappe.get_all(
        DESIGN_DOCTYPE,
        fields=[
            "name",
            "design_id",
            "status",
            "design_status",
            "design_approved",
            "design_source_locked",
            "design_shape_locked",
            "candidate_selection_not_started",
            "design_source_doctype",
            "design_reference_doctype",
            "design_party_type",
            "design_line_count",
            "design_total_amount",
            "design_payment_entry_count",
            "ready_for_governed_limited_operation_candidate_selection_gate",
            "monitored_payment_entry",
            "payment_entry_docstatus_design",
            "payment_entry_status_design",
            "monitored_reference_count",
            "monitored_total_amount",
            "monitored_voucher_gl_rows",
            "monitored_voucher_gl_net",
            "monitored_restored_invoice_amount",
            "planning",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "design_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
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
            "allocated_amount",
            "current_outstanding_amount",
            "monitored_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "design_records": records,
        "items": items,
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "note": "Phase 12C governed limited-operation design summary.",
    }


def execute_design_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("d.status = %(status)s")
        params["status"] = filters.get("status")

    columns = design_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            d.name AS design,
            d.design_id,
            d.status,
            d.design_status,
            d.design_approved,
            d.phase12b_planning_verified,
            d.planning_approved_verified,
            d.planning_envelope_locked_verified,
            d.planning_source_locked_verified,
            d.planning_shape_locked_verified,
            d.candidate_selection_not_started_verified,
            d.design_source_locked,
            d.design_shape_locked,
            d.candidate_selection_not_started,
            d.live_posting_not_allowed_verified,
            d.journal_entry_side_effect_not_allowed_verified,
            d.purchase_invoice_side_effect_not_allowed_verified,
            d.no_new_accounting_movement_verified,
            d.policy_state_preserved_verified,
            d.ready_for_governed_limited_operation_candidate_selection_gate,
            d.design_source_doctype,
            d.design_reference_doctype,
            d.design_party_type,
            d.design_line_count,
            d.design_total_amount,
            d.design_payment_entry_count,
            d.design_live_posting_allowed,
            d.design_journal_entry_side_effect_allowed,
            d.design_purchase_invoice_side_effect_allowed,
            d.monitored_payment_entry,
            d.payment_entry_docstatus_design,
            d.payment_entry_status_design,
            d.monitored_reference_count,
            d.monitored_total_amount,
            d.monitored_voucher_gl_rows,
            d.monitored_voucher_gl_net,
            d.monitored_restored_invoice_amount,
            d.planning,
            d.payment_entry_count_before,
            d.payment_entry_count_after,
            d.payment_entry_gl_count_before,
            d.payment_entry_gl_count_after,
            d.actual_payment_entry_created_count,
            d.actual_payment_entry_cancelled_count,
            d.actual_gl_created_count,
            d.submitted_journal_entry_count_today,
            d.purchase_invoice_count_today,
            d.design_score,
            d.checked_on,
            %(currency)s AS currency
        FROM `tab{DESIGN_DOCTYPE}` d
        {build_where(conditions)}
        ORDER BY d.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.design_id for row in data[:20]],
            "datasets": [
                {"name": "Design Approved", "values": [int(row.design_approved or 0) for row in data[:20]]},
                {"name": "Candidate Selection Ready", "values": [int(row.ready_for_governed_limited_operation_candidate_selection_gate or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Records"), "datatype": "Int"},
        {"value": sum(int(row.design_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_governed_limited_operation_candidate_selection_gate or 0) for row in data), "indicator": "Green", "label": _("Candidate Selection Ready"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def design_columns():
    return [
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "design_id", "label": _("Design ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "design_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase12b_planning_verified", "label": _("12B Verified"), "fieldtype": "Check", "width": 105},
        {"fieldname": "planning_approved_verified", "label": _("Planning OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "planning_envelope_locked_verified", "label": _("Envelope OK"), "fieldtype": "Check", "width": 105},
        {"fieldname": "planning_source_locked_verified", "label": _("Source OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "planning_shape_locked_verified", "label": _("Shape OK"), "fieldtype": "Check", "width": 95},
        {"fieldname": "candidate_selection_not_started_verified", "label": _("Candidate Not Started OK"), "fieldtype": "Check", "width": 150},
        {"fieldname": "design_source_locked", "label": _("Design Source Locked"), "fieldtype": "Check", "width": 135},
        {"fieldname": "design_shape_locked", "label": _("Design Shape Locked"), "fieldtype": "Check", "width": 130},
        {"fieldname": "candidate_selection_not_started", "label": _("Candidate Not Started"), "fieldtype": "Check", "width": 145},
        {"fieldname": "live_posting_not_allowed_verified", "label": _("Live Disabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "journal_entry_side_effect_not_allowed_verified", "label": _("JE Disabled"), "fieldtype": "Check", "width": 105},
        {"fieldname": "purchase_invoice_side_effect_not_allowed_verified", "label": _("PI Disabled"), "fieldtype": "Check", "width": 105},
        {"fieldname": "no_new_accounting_movement_verified", "label": _("No Movement"), "fieldtype": "Check", "width": 110},
        {"fieldname": "policy_state_preserved_verified", "label": _("Policy OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_candidate_selection_gate", "label": _("Candidate Ready"), "fieldtype": "Check", "width": 125},
        {"fieldname": "design_source_doctype", "label": _("Source"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_reference_doctype", "label": _("Reference"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "design_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
        {"fieldname": "design_total_amount", "label": _("Design Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "design_payment_entry_count", "label": _("Future PE"), "fieldtype": "Int", "width": 85},
        {"fieldname": "design_live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "design_journal_entry_side_effect_allowed", "label": _("JE Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "design_purchase_invoice_side_effect_allowed", "label": _("PI Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "monitored_payment_entry", "label": _("Monitored PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_design", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_design", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "monitored_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "monitored_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "monitored_voucher_gl_rows", "label": _("GL Rows"), "fieldtype": "Int", "width": 85},
        {"fieldname": "monitored_voucher_gl_net", "label": _("GL Net"), "fieldtype": "Currency", "options": "currency", "width": 90},
        {"fieldname": "monitored_restored_invoice_amount", "label": _("Restored"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "planning", "label": _("Planning"), "fieldtype": "Link", "options": PLANNING_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("design"):
        conditions.append("i.design = %(design)s")
        params["design"] = filters.get("design")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": DESIGN_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 210},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "allocated_amount", "label": _("Allocated Amount"), "fieldtype": "Currency", "width": 120},
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
            i.design,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.current_outstanding_amount,
            i.monitored_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{DESIGN_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Design Envelope Reference"]), "indicator": "Green", "label": _("Design References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Design Envelope Reference"), "indicator": "Green", "label": _("Design Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_design_report(filters)
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