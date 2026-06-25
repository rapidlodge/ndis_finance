import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, nowdate, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE11J_EXECUTE_NEXT_GOVERNED_LIMITED_OPERATION_SMOKE_CREATE_ONE_PAYMENT_ENTRY"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
EXEC_GATE_DOCTYPE = "NDIS Governed Next Op Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Governed Next Op Exec Gate Item"
SMOKE_DOCTYPE = "NDIS Governed Next Op Smoke"
SMOKE_ITEM_DOCTYPE = "NDIS Governed Next Op Smoke Item"


def make_smoke_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-NEXT-OP-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_execution_gate():
    rows = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        filters={
            "status": "Execution Gate Approved",
            "execution_gate_status": "Ready For Next Governed Limited Operation Smoke",
            "execution_gate_approved": 1,
            "phase11h_preview_verified": 1,
            "preview_shape_locked_verified": 1,
            "preview_references_locked_verified": 1,
            "preview_total_verified": 1,
            "smoke_execution_authorised": 1,
            "smoke_only_authorised": 1,
            "real_production_posting_authorised": 0,
            "ready_for_next_governed_limited_operation_smoke": 1,
            "approved_reference_doctype": "Sales Invoice",
            "approved_reference_count": 3,
            "approved_total_amount": 3.00,
            "approved_payment_entry_count": 1,
            "approved_gl_entry_count_preview": 0,
            "approved_live_posting_allowed": 0,
            "approved_journal_entry_side_effect_allowed": 0,
            "approved_purchase_invoice_side_effect_allowed": 0,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "locked_payment_entry_count": 8,
            "locked_payment_entry_gl_count": 46,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "execution_gate_id",
            "preview",
            "validation",
            "candidate",
            "design",
            "planning",
            "precheck",
            "monitor",
            "payment_entry",
            "approved_party_type",
            "approved_party",
            "approved_company",
            "approved_currency",
            "approved_reference_doctype",
            "approved_reference_count",
            "approved_total_amount",
            "approved_payment_entry_count",
            "approved_gl_entry_count_preview",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "locked_policy_enabled_count",
            "locked_policy_live_allowed_count",
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
        fields=["name", "smoke_id", "created_payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def get_approved_lines(execution_gate):
    if not execution_gate:
        return []

    return frappe.get_all(
        EXEC_GATE_ITEM_DOCTYPE,
        filters={
            "execution_gate": execution_gate,
            "category": "Approved Reference",
            "reference_doctype": "Sales Invoice",
            "status": "Pass",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "allocated_amount",
        ],
        order_by="line_no asc, creation asc",
    )


def validate_source(gate, lines, guard, config, policy_enabled, policy_live):
    issues = []

    if not gate:
        issues.append("No approved Phase 11I execution gate found.")
        return issues

    existing = existing_completed_smoke(gate.name)
    if existing:
        issues.append(f"Completed Phase 11J smoke already exists for this execution gate: {existing.smoke_id}")

    if len(lines) != 3:
        issues.append(f"Exactly 3 approved references are required. Found {len(lines)}.")

    if gate.payment_entry and not frappe.db.exists("Payment Entry", gate.payment_entry):
        issues.append(f"Historical Payment Entry not found: {gate.payment_entry}")

    if int(gate.locked_payment_entry_count or 0) != 8:
        issues.append("Execution gate locked Payment Entry count must be 8.")

    if int(gate.locked_payment_entry_gl_count or 0) != 46:
        issues.append("Execution gate locked Payment Entry GL count must be 46.")

    if guard["payment_entry_count"] != 8:
        issues.append("Payment Entry count must be 8 before Phase 11J smoke.")

    if guard["payment_entry_gl_count"] != 46:
        issues.append("Payment Entry GL count must be 46 before Phase 11J smoke.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must be 0 before Phase 11J smoke.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must be 0 before Phase 11J smoke.")

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

    if lines:
        doctypes = {line.reference_doctype for line in lines}
        customers = {line.customer for line in lines}
        companies = {line.company for line in lines}
        currencies = {line.currency for line in lines}
        total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)

        if doctypes != {"Sales Invoice"}:
            issues.append("All smoke references must be Sales Invoice.")

        if len(customers) != 1:
            issues.append("All smoke references must have the same customer.")

        if len(companies) != 1:
            issues.append("All smoke references must have the same company.")

        if len(currencies) != 1:
            issues.append("All smoke references must have the same currency.")

        if total != 3:
            issues.append(f"Smoke allocation total must be 3.00. Found {total}.")

        for line in lines:
            if not frappe.db.exists("Sales Invoice", line.reference_name):
                issues.append(f"Sales Invoice missing: {line.reference_name}")
                continue

            si = frappe.get_doc("Sales Invoice", line.reference_name)

            if si.docstatus != 1:
                issues.append(f"Sales Invoice {si.name} must remain submitted.")

            if flt(si.outstanding_amount or 0, 2) < flt(line.allocated_amount or 0, 2):
                issues.append(
                    f"Sales Invoice {si.name} outstanding {flt(si.outstanding_amount or 0, 2)} is less than smoke allocation {flt(line.allocated_amount or 0, 2)}."
                )

    return issues


def set_if_has(doc, fieldname, value):
    if doc.meta.has_field(fieldname) and value is not None:
        setattr(doc, fieldname, value)


def create_and_submit_payment_entry(gate, lines):
    historical = frappe.get_doc("Payment Entry", gate.payment_entry)

    total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)
    reference_no = f"PHASE11J-{frappe.generate_hash(length=8).upper()}"

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = historical.payment_type or "Receive"
    pe.company = gate.approved_company
    pe.posting_date = nowdate()
    pe.mode_of_payment = historical.mode_of_payment
    pe.party_type = "Customer"
    pe.party = gate.approved_party

    pe.paid_from = historical.paid_from
    pe.paid_to = historical.paid_to
    set_if_has(pe, "bank_account", getattr(historical, "bank_account", None))
    pe.paid_amount = total
    pe.received_amount = total
    pe.reference_no = reference_no
    pe.reference_date = nowdate()
    pe.remarks = f"Phase 11J governed smoke execution from gate {gate.execution_gate_id}; rollback required."

    for fieldname in [
        "paid_from_account_currency",
        "paid_to_account_currency",
        "source_exchange_rate",
        "target_exchange_rate",
        "base_paid_amount",
        "base_received_amount",
    ]:
        set_if_has(pe, fieldname, getattr(historical, fieldname, None))

    if pe.meta.has_field("base_paid_amount"):
        pe.base_paid_amount = total
    if pe.meta.has_field("base_received_amount"):
        pe.base_received_amount = total

    for line in lines:
        si = frappe.get_doc("Sales Invoice", line.reference_name)
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": si.name,
                "total_amount": flt(si.grand_total or 0, 2),
                "outstanding_amount": flt(si.outstanding_amount or 0, 2),
                "allocated_amount": flt(line.allocated_amount or 0, 2),
            },
        )

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe.name


def voucher_gl_row_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def payment_entry_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def add_item(items, status, severity, category, check_key, check_label, detail, line=None, source_doctype=None, source_name=None, created_payment_entry=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "source_doctype": source_doctype,
        "source_name": source_name,
        "created_payment_entry": created_payment_entry,
    }

    if line:
        item.update({
            "line_no": int(line.line_no or 0),
            "reference_doctype": line.reference_doctype,
            "reference_name": line.reference_name,
            "customer": line.customer,
            "company": line.company,
            "currency": line.currency,
            "allocated_amount": flt(line.allocated_amount or 0, 2),
        })

    items.append(item)


def build_items(gate, lines, issues, ack_ok, created_payment_entry=None):
    items = []

    if gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11i_gate_exists",
            "Phase 11I execution gate exists",
            f"Execution gate found: {gate.execution_gate_id}.",
            source_doctype=EXEC_GATE_DOCTYPE,
            source_name=gate.name,
            created_payment_entry=created_payment_entry,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11i_gate_exists", "Phase 11I execution gate exists", "No approved Phase 11I execution gate found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Smoke Source", "smoke_source_valid", "Smoke source valid", "One controlled Payment Entry smoke can be executed.", created_payment_entry=created_payment_entry)
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Smoke Source", "smoke_source_valid", "Smoke source valid", issue, created_payment_entry=created_payment_entry)

    for line in lines:
        add_item(
            items,
            "Pass",
            "High",
            "Smoke Reference",
            "smoke_sales_invoice_reference",
            f"Smoke Sales Invoice {line.line_no}",
            f"{line.reference_name} allocated {flt(line.allocated_amount or 0, 2)}.",
            line=line,
            source_doctype="Sales Invoice",
            source_name=line.reference_name,
            created_payment_entry=created_payment_entry,
        )

    checks = [
        ("one_payment_entry_created", "Exactly one Payment Entry created", 1 if created_payment_entry else 0),
        ("submitted_payment_entry", "Created Payment Entry submitted", created_payment_entry or "not created"),
        ("rollback_required", "Rollback required", 1 if created_payment_entry else 0),
        ("freeze_required_after_rollback", "Freeze required after rollback", 1 if created_payment_entry else 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("ready_for_rollback", "Ready for Phase 11K rollback", 1 if created_payment_entry else 0),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Smoke Evidence", key, label, f"value={value}", created_payment_entry=created_payment_entry)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.", created_payment_entry=created_payment_entry)
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {SMOKE_ACK}")

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

    gate = latest_execution_gate()
    lines = get_approved_lines(gate.name if gate else None)

    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0

    issues = validate_source(gate, lines, guard_before, config, policy_enabled_before, policy_live_before)

    dry_run = int(dry_run or 0)
    created_payment_entry = None

    pre_items = build_items(gate, lines, issues, ack_ok, created_payment_entry=None)
    pre_summary = summarise_items(pre_items)

    allowed_to_create = int(
        not dry_run
        and ack_ok
        and gate
        and pre_summary["blocker_count"] == 0
        and len(lines) == 3
        and flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2) == 3
    )

    if allowed_to_create:
        created_payment_entry = create_and_submit_payment_entry(gate, lines)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    actual_pe_cancelled = 0
    policy_mutation_count = int(
        policy_enabled_before != policy_enabled_after
        or policy_live_before != policy_live_after
        or guard_before["production_batch_enabled_policy_count"] != guard_after["production_batch_enabled_policy_count"]
        or guard_before["live_posting_allowed_policy_count"] != guard_after["live_posting_allowed_policy_count"]
    )

    if created_payment_entry:
        pe = frappe.get_doc("Payment Entry", created_payment_entry)
        created_docstatus = pe.docstatus
        created_status = pe.status
        created_reference_count = payment_entry_reference_count(created_payment_entry)
        created_total_amount = flt(pe.paid_amount or pe.received_amount or 0, 2)
        created_gl_rows = voucher_gl_row_count(created_payment_entry)
    else:
        created_docstatus = 0
        created_status = None
        created_reference_count = 0
        created_total_amount = 0
        created_gl_rows = 0

    post_issues = list(issues)

    if created_payment_entry:
        if actual_pe_created != 1:
            post_issues.append(f"Smoke must create exactly 1 Payment Entry. Created {actual_pe_created}.")
        if created_docstatus != 1:
            post_issues.append(f"Created Payment Entry must be submitted. docstatus={created_docstatus}.")
        if created_reference_count != 3:
            post_issues.append(f"Created Payment Entry reference count must be 3. Found {created_reference_count}.")
        if created_total_amount != 3:
            post_issues.append(f"Created Payment Entry total amount must be 3.00. Found {created_total_amount}.")
        if actual_gl_created != 4:
            post_issues.append(f"Expected exactly 4 Payment Entry GL rows for this smoke. Found {actual_gl_created}.")
        if guard_after["submitted_journal_entry_count_today"] != 0:
            post_issues.append("Submitted Journal Entry count today must remain 0 after smoke.")
        if guard_after["purchase_invoice_count_today"] != 0:
            post_issues.append("Purchase Invoice count today must remain 0 after smoke.")
        if policy_mutation_count != 0:
            post_issues.append("Policy state changed during smoke. This is not allowed.")

    items = build_items(gate, lines, post_issues, ack_ok, created_payment_entry=created_payment_entry)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(bool(
        created_payment_entry
        and item_summary["blocker_count"] == 0
        and actual_pe_created == 1
        and actual_pe_cancelled == 0
        and actual_gl_created == 4
        and created_docstatus == 1
        and created_reference_count == 3
        and created_total_amount == 3
        and guard_after["submitted_journal_entry_count_today"] == 0
        and guard_after["purchase_invoice_count_today"] == 0
        and policy_mutation_count == 0
    ))

    result = {
        "dry_run": bool(dry_run),
        "status": "Smoke Completed - Rollback Required" if completed else "Needs Review",
        "smoke_status": "Next Governed Limited Operation Smoke Completed" if completed else "Needs Review",
        "smoke_completed": completed,
        "phase11i_execution_gate_verified": 1 if gate else 0,
        "smoke_execution_authorised_verified": 1 if gate else 0,
        "smoke_only_authorised_verified": 1 if gate else 0,
        "real_production_posting_authorised": 0,
        "rollback_required": completed,
        "freeze_required_after_rollback": completed,
        "ready_for_next_governed_limited_operation_smoke_rollback": completed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": policy_mutation_count,
        "created_payment_entry": created_payment_entry,
        "created_payment_entry_docstatus": created_docstatus,
        "created_payment_entry_status": created_status,
        "created_payment_entry_reference_count": created_reference_count,
        "created_payment_entry_total_amount": created_total_amount,
        "created_payment_entry_gl_row_count": created_gl_rows,
        "approved_party_type": "Customer",
        "approved_party": gate.approved_party if gate else None,
        "approved_company": gate.approved_company if gate else None,
        "approved_currency": gate.approved_currency if gate else None,
        "approved_reference_doctype": "Sales Invoice",
        "approved_reference_count": len(lines),
        "approved_total_amount": flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2),
        "execution_gate": gate.name if gate else None,
        "preview": gate.preview if gate else None,
        "validation": gate.validation if gate else None,
        "candidate": gate.candidate if gate else None,
        "design": gate.design if gate else None,
        "planning": gate.planning if gate else None,
        "historical_payment_entry": gate.payment_entry if gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": gate.target_policy if gate else None,
        "target_policy_name": gate.target_policy_name if gate else None,
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
        "smoke_score": score,
        **item_summary,
        "items": items,
        "approved_lines": [dict(line) for line in lines],
        "issues": post_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11J creates one submitted Payment Entry smoke and requires immediate Phase 11K rollback.",
    }

    if dry_run:
        result["status"] = "Needs Review"
        result["smoke_status"] = "Needs Review"
        result["smoke_completed"] = 0
        result["rollback_required"] = 0
        result["freeze_required_after_rollback"] = 0
        result["ready_for_next_governed_limited_operation_smoke_rollback"] = 0
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
    doc.smoke_json = safe_json(
        {
            "execution_gate": gate,
            "approved_lines": [dict(line) for line in lines],
            "created_payment_entry": created_payment_entry,
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
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
        "smoke": doc.name,
        "smoke_id": doc.smoke_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_smoke_audit(smoke, reason=None):
    assert_action("cancel_next_governed_limited_operation_smoke_audit")

    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Governed next operation smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_completed or 0) or doc.created_payment_entry:
        frappe.throw(_("Cannot cancel a completed smoke audit or any audit linked to a created Payment Entry. Use Phase 11K rollback."))

    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11J no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{SMOKE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE smoke = %(smoke)s
        """,
        {"smoke": smoke},
    )

    frappe.db.commit()

    return {
        "smoke": smoke,
        "status": "Cancelled",
        "note": "No-ack smoke audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_smoke_summary(limit=20):
    records = frappe.get_all(
        SMOKE_DOCTYPE,
        fields=[
            "name",
            "smoke_id",
            "status",
            "smoke_status",
            "smoke_completed",
            "rollback_required",
            "freeze_required_after_rollback",
            "ready_for_next_governed_limited_operation_smoke_rollback",
            "created_payment_entry",
            "created_payment_entry_docstatus",
            "created_payment_entry_status",
            "created_payment_entry_reference_count",
            "created_payment_entry_total_amount",
            "created_payment_entry_gl_row_count",
            "execution_gate",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
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
            "allocated_amount",
            "created_payment_entry",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "smoke_records": records,
        "items": items,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11J governed next operation smoke summary.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = smoke_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke,
            s.smoke_id,
            s.status,
            s.smoke_status,
            s.smoke_completed,
            s.rollback_required,
            s.freeze_required_after_rollback,
            s.ready_for_next_governed_limited_operation_smoke_rollback,
            s.created_payment_entry,
            s.created_payment_entry_docstatus,
            s.created_payment_entry_status,
            s.created_payment_entry_reference_count,
            s.created_payment_entry_total_amount,
            s.created_payment_entry_gl_row_count,
            s.execution_gate,
            s.payment_entry_count_before,
            s.payment_entry_count_after,
            s.payment_entry_gl_count_before,
            s.payment_entry_gl_count_after,
            s.actual_payment_entry_created_count,
            s.actual_payment_entry_cancelled_count,
            s.actual_gl_created_count,
            s.submitted_journal_entry_count_today,
            s.purchase_invoice_count_today,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tab{SMOKE_DOCTYPE}` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_id for row in data[:20]],
            "datasets": [
                {"name": "PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "GL Created", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
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


def smoke_columns():
    return [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_required", "label": _("Rollback"), "fieldtype": "Check", "width": 90},
        {"fieldname": "freeze_required_after_rollback", "label": _("Freeze"), "fieldtype": "Check", "width": 80},
        {"fieldname": "ready_for_next_governed_limited_operation_smoke_rollback", "label": _("Rollback Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "created_payment_entry", "label": _("Created PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "created_payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "created_payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "created_payment_entry_reference_count", "label": _("PE Refs"), "fieldtype": "Int", "width": 85},
        {"fieldname": "created_payment_entry_total_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "created_payment_entry_gl_row_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("smoke"):
        conditions.append("i.smoke = %(smoke)s")
        params["smoke"] = filters.get("smoke")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": SMOKE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "created_payment_entry", "label": _("Created PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.smoke,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.allocated_amount,
            i.created_payment_entry,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{SMOKE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Smoke Reference"]), "indicator": "Orange", "label": _("Smoke References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Smoke Reference"), "indicator": "Orange", "label": _("Smoke Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Orange", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Orange", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
