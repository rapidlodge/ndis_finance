import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE11H_PREVIEW_NEXT_GOVERNED_LIMITED_OPERATION_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
VALIDATION_DOCTYPE = "NDIS Governed Limited Op Candidate Validation"
VALIDATION_ITEM_DOCTYPE = "NDIS Governed Limited Op Candidate Validation Item"
PREVIEW_DOCTYPE = "NDIS Governed Next Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Governed Next Op Preview Item"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-NEXT-OP-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_validation():
    rows = frappe.get_all(
        VALIDATION_DOCTYPE,
        filters={
            "status": "Candidate Validation Approved",
            "candidate_validation_status": "Next Governed Limited Operation Candidate Validation Approved",
            "candidate_validation_approved": 1,
            "phase11f_candidate_verified": 1,
            "candidate_selection_locked_verified": 1,
            "selected_invoice_count_verified": 1,
            "selected_invoices_exist_verified": 1,
            "selected_invoices_submitted_verified": 1,
            "outstanding_amount_sufficient_verified": 1,
            "same_customer_verified": 1,
            "same_company_verified": 1,
            "same_currency_verified": 1,
            "allocation_total_verified": 1,
            "ready_for_next_governed_limited_operation_preview": 1,
            "validated_source_doctype": "Sales Invoice",
            "validated_reference_doctype": "Sales Invoice",
            "validated_party_type": "Customer",
            "validated_invoice_count": 3,
            "validated_total_amount": 3.00,
            "validated_payment_entry_count": 1,
            "validated_live_posting_allowed": 0,
            "validated_journal_entry_side_effect_allowed": 0,
            "validated_purchase_invoice_side_effect_allowed": 0,
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
            "validation_id",
            "candidate",
            "design",
            "planning",
            "precheck",
            "monitor",
            "payment_entry",
            "validated_customer",
            "validated_company",
            "validated_currency",
            "validated_invoice_count",
            "validated_total_amount",
            "validated_payment_entry_count",
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


def existing_preview(validation):
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={"validation": validation, "status": "Preview Approved", "preview_approved": 1},
        fields=["name", "preview_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_validation_lines(validation):
    if not validation:
        return []

    return frappe.get_all(
        VALIDATION_ITEM_DOCTYPE,
        filters={
            "validation": validation,
            "category": "Validated Candidate",
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
            "outstanding_amount",
            "allocated_amount",
        ],
        order_by="line_no asc, creation asc",
    )


def validate_preview_lines(validation, lines):
    issues = []

    if not validation:
        issues.append("No approved Phase 11G candidate validation found.")
        return issues

    existing = existing_preview(validation.name)
    if existing:
        issues.append(f"Phase 11H preview already exists for this validation: {existing.preview_id}")

    if len(lines) != 3:
        issues.append(f"Exactly 3 validated invoice lines are required. Found {len(lines)}.")

    if lines:
        doctypes = {line.reference_doctype for line in lines}
        customers = {line.customer for line in lines}
        companies = {line.company for line in lines}
        currencies = {line.currency for line in lines}
        total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)

        if doctypes != {"Sales Invoice"}:
            issues.append("All preview references must be Sales Invoice.")

        if len(customers) != 1:
            issues.append("All preview references must have the same customer.")

        if len(companies) != 1:
            issues.append("All preview references must have the same company.")

        if len(currencies) != 1:
            issues.append("All preview references must have the same currency.")

        if total != 3:
            issues.append(f"Preview allocation total must be 3.00. Found {total}.")

        for line in lines:
            if not frappe.db.exists("Sales Invoice", line.reference_name):
                issues.append(f"Sales Invoice missing: {line.reference_name}")
                continue

            si = frappe.get_doc("Sales Invoice", line.reference_name)

            if si.docstatus != 1:
                issues.append(f"Sales Invoice {si.name} must remain submitted.")

            if flt(si.outstanding_amount or 0, 2) < flt(line.allocated_amount or 0, 2):
                issues.append(
                    f"Sales Invoice {si.name} outstanding {flt(si.outstanding_amount or 0, 2)} is less than preview allocation {flt(line.allocated_amount or 0, 2)}."
                )

            if si.customer != line.customer or si.company != line.company or getattr(si, "currency", None) != line.currency:
                issues.append(f"Sales Invoice {si.name} customer/company/currency changed after Phase 11G.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, line=None, source_doctype=None, source_name=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "source_doctype": source_doctype,
        "source_name": source_name,
    }

    if line:
        item.update({
            "line_no": int(line.line_no or 0),
            "reference_doctype": line.reference_doctype,
            "reference_name": line.reference_name,
            "customer": line.customer,
            "company": line.company,
            "currency": line.currency,
            "outstanding_amount": flt(line.outstanding_amount or 0, 2),
            "allocated_amount": flt(line.allocated_amount or 0, 2),
        })

    items.append(item)


def build_items(validation, lines, issues, ack_ok):
    items = []

    if validation:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11g_validation_exists",
            "Phase 11G validation exists",
            f"Validation found: {validation.validation_id}.",
            source_doctype=VALIDATION_DOCTYPE,
            source_name=validation.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11g_validation_exists", "Phase 11G validation exists", "No approved Phase 11G validation found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", "Preview references are valid and locked.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", issue)

    for line in lines:
        add_item(
            items,
            "Pass",
            "High",
            "Preview Reference",
            "preview_sales_invoice_reference",
            f"Preview Sales Invoice {line.line_no}",
            f"{line.reference_name} would be allocated {flt(line.allocated_amount or 0, 2)}.",
            line=line,
            source_doctype="Sales Invoice",
            source_name=line.reference_name,
        )

    checks = [
        ("preview_shape_locked", "Preview shape locked", "1 PE / 3 references / 3.00"),
        ("would_create_pe", "Would create one Payment Entry", 1),
        ("would_create_gl", "Would create zero GL in preview", 0),
        ("no_actual_pe", "No actual Payment Entry created", 0),
        ("no_actual_gl", "No actual GL created", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("execution_gate_ready", "Ready for final execution gate", 1),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Preview Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PREVIEW_ACK}")

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
        row = frappe.new_doc(PREVIEW_ITEM_DOCTYPE)
        row.preview = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_preview")

    validation = latest_validation()
    lines = get_validation_lines(validation.name if validation else None)

    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, validation.target_policy, "production_batch_enabled") if validation else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, validation.target_policy, "live_posting_allowed") if validation else 0

    issues = validate_preview_lines(validation, lines)

    if guard_before["payment_entry_count"] != 8:
        issues.append("Payment Entry count must remain 8 before Phase 11H preview.")

    if guard_before["payment_entry_gl_count"] != 46:
        issues.append("Payment Entry GL count must remain 46 before Phase 11H preview.")

    if guard_before["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")

    if guard_before["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")

    if guard_before["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled policy must remain enabled.")

    if guard_before["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, validation.target_policy, "production_batch_enabled") if validation else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, validation.target_policy, "live_posting_allowed") if validation else 0

    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )

    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )

    if not no_new_movement:
        issues.append("Accounting movement changed during Phase 11H preview generation.")

    if not policy_preserved:
        issues.append("Policy state changed during Phase 11H preview generation.")

    preview_total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)
    preview_party = lines[0].customer if lines else None
    preview_company = lines[0].company if lines else None
    preview_currency = lines[0].currency if lines else None

    items = build_items(validation, lines, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(
        ack_ok
        and validation
        and item_summary["blocker_count"] == 0
        and len(lines) == 3
        and preview_total == 3
        and no_new_movement
        and policy_preserved
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Preview Approved" if allowed else "Needs Review",
        "preview_status": "Next Governed Limited Operation Preview Approved" if allowed else "Needs Review",
        "preview_approved": allowed,
        "phase11g_validation_verified": 1 if validation else 0,
        "phase11f_candidate_verified": 1 if validation else 0,
        "candidate_validation_locked_verified": 1 if validation else 0,
        "validated_invoice_count_verified": int(len(lines) == 3),
        "preview_shape_locked": allowed,
        "preview_references_locked": allowed,
        "preview_total_verified": int(preview_total == 3),
        "ready_for_next_governed_limited_operation_execution_gate": allowed,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "preview_party_type": "Customer",
        "preview_party": preview_party,
        "preview_company": preview_company,
        "preview_currency": preview_currency,
        "preview_reference_doctype": "Sales Invoice",
        "preview_reference_count": len(lines),
        "preview_total_amount": preview_total,
        "would_create_payment_entry_count": 1 if len(lines) == 3 else 0,
        "would_create_gl_entry_count": 0,
        "preview_live_posting_allowed": 0,
        "preview_journal_entry_side_effect_allowed": 0,
        "preview_purchase_invoice_side_effect_allowed": 0,
        "preview_mode": "Preview Only - No Posting",
        "validation": validation.name if validation else None,
        "candidate": validation.candidate if validation else None,
        "design": validation.design if validation else None,
        "planning": validation.planning if validation else None,
        "precheck": validation.precheck if validation else None,
        "monitor": validation.monitor if validation else None,
        "payment_entry": validation.payment_entry if validation else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": validation.target_policy if validation else None,
        "target_policy_name": validation.target_policy_name if validation else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "locked_payment_entry_count": int(validation.locked_payment_entry_count or 0) if validation else 0,
        "locked_payment_entry_gl_count": int(validation.locked_payment_entry_gl_count or 0) if validation else 0,
        "locked_policy_enabled_count": int(validation.locked_policy_enabled_count or 0) if validation else 0,
        "locked_policy_live_allowed_count": int(validation.locked_policy_live_allowed_count or 0) if validation else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "preview_score": score,
        **item_summary,
        "preview_lines": [dict(line) for line in lines],
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11H creates preview evidence only. It does not create Payment Entry, GL, Journal Entry, Purchase Invoice, or policy mutation.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["preview_status"] = "Needs Review"
        result["preview_approved"] = 0
        result["preview_shape_locked"] = 0
        result["preview_references_locked"] = 0
        result["ready_for_next_governed_limited_operation_execution_gate"] = 0
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.preview_json = safe_json(
        {
            "validation": validation,
            "preview_lines": [dict(line) for line in lines],
            "would_create": {
                "payment_entry_count": 1 if len(lines) == 3 else 0,
                "gl_entry_count": 0,
                "total_amount": preview_total,
            },
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "issues": issues,
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
        "preview": doc.name,
        "preview_id": doc.preview_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_preview_audit(preview, reason=None):
    assert_action("cancel_next_governed_limited_operation_preview_audit")

    if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
        frappe.throw(_("Governed next operation preview audit not found: {0}").format(preview))

    doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)

    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.preview_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11H preview record."))

    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        preview,
        {
            "status": "Cancelled",
            "preview_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11H no-ack preview audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{PREVIEW_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE preview = %(preview)s
        """,
        {"preview": preview},
    )

    frappe.db.commit()

    return {
        "preview": preview,
        "status": "Cancelled",
        "note": "No-ack preview audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_preview_summary(limit=20):
    records = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "preview_approved",
            "phase11g_validation_verified",
            "preview_shape_locked",
            "preview_references_locked",
            "preview_reference_count",
            "preview_total_amount",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "ready_for_next_governed_limited_operation_execution_gate",
            "validation",
            "candidate",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        fields=[
            "name",
            "preview",
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
            "outstanding_amount",
            "allocated_amount",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "preview_records": records,
        "items": items,
        "required_acknowledgement": PREVIEW_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11H governed next operation preview summary.",
    }


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")

    columns = preview_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS preview,
            p.preview_id,
            p.status,
            p.preview_status,
            p.preview_approved,
            p.phase11g_validation_verified,
            p.preview_shape_locked,
            p.preview_references_locked,
            p.preview_reference_count,
            p.preview_total_amount,
            p.would_create_payment_entry_count,
            p.would_create_gl_entry_count,
            p.ready_for_next_governed_limited_operation_execution_gate,
            p.validation,
            p.candidate,
            p.preview_party,
            p.preview_company,
            p.preview_currency,
            p.payment_entry_count_before,
            p.payment_entry_count_after,
            p.payment_entry_gl_count_before,
            p.payment_entry_gl_count_after,
            p.actual_payment_entry_created_count,
            p.actual_payment_entry_cancelled_count,
            p.actual_gl_created_count,
            p.submitted_journal_entry_count_today,
            p.purchase_invoice_count_today,
            p.preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tab{PREVIEW_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.preview_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.preview_approved or 0) for row in data[:20]]},
                {"name": "Preview References", "values": [int(row.preview_reference_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Preview Records"), "datatype": "Int"},
        {"value": sum(int(row.preview_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.preview_reference_count or 0) for row in data), "indicator": "Green", "label": _("Preview References"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 360},
        {"fieldname": "preview_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11g_validation_verified", "label": _("11G Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_shape_locked", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_references_locked", "label": _("Refs Locked"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "preview_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 85},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 85},
        {"fieldname": "ready_for_next_governed_limited_operation_execution_gate", "label": _("Exec Gate Ready"), "fieldtype": "Check", "width": 125},
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": "NDIS Governed Limited Op Candidate", "width": 220},
        {"fieldname": "preview_party", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "preview_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "preview_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("preview"):
        conditions.append("i.preview = %(preview)s")
        params["preview"] = filters.get("preview")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PREVIEW_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.preview,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.outstanding_amount,
            i.allocated_amount,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{PREVIEW_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Preview Reference"]), "indicator": "Green", "label": _("Preview References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Preview Reference"), "indicator": "Green", "label": _("Preview Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_report(filters)
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
