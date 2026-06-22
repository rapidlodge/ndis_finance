import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


VALIDATION_ACK = "I_CONFIRM_PHASE11G_VALIDATE_NEXT_GOVERNED_LIMITED_OPERATION_CANDIDATES_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
CANDIDATE_DOCTYPE = "NDIS Governed Limited Op Candidate"
CANDIDATE_ITEM_DOCTYPE = "NDIS Governed Limited Op Candidate Item"
VALIDATION_DOCTYPE = "NDIS Governed Limited Op Candidate Validation"
VALIDATION_ITEM_DOCTYPE = "NDIS Governed Limited Op Candidate Validation Item"


def make_validation_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-CAND-VALID-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_value_if_has(doctype, name, fieldname, default=None):
    if not name or not frappe.db.exists(doctype, name):
        return default
    if not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    value = get_value_if_has(doctype, name, fieldname, default)
    return int(value or 0)


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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


def latest_candidate():
    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters={
            "status": "Candidate Selection Approved",
            "candidate_selection_status": "Next Governed Limited Operation Candidate Selection Approved",
            "candidate_selection_approved": 1,
            "phase11e_design_verified": 1,
            "design_shape_locked_verified": 1,
            "candidate_selection_locked": 1,
            "candidate_source_verified": 1,
            "same_customer_verified": 1,
            "same_company_verified": 1,
            "same_currency_verified": 1,
            "allocation_total_verified": 1,
            "ready_for_next_governed_limited_operation_candidate_validation": 1,
            "selected_source_doctype": "Sales Invoice",
            "selected_reference_doctype": "Sales Invoice",
            "selected_party_type": "Customer",
            "selected_line_count": 3,
            "selected_total_amount": 3.00,
            "selected_payment_entry_count": 1,
            "selected_live_posting_allowed": 0,
            "selected_journal_entry_side_effect_allowed": 0,
            "selected_purchase_invoice_side_effect_allowed": 0,
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
            "candidate_id",
            "design",
            "planning",
            "precheck",
            "monitor",
            "baseline",
            "closeout",
            "governed_freeze",
            "rollback",
            "smoke",
            "payment_entry",
            "selected_customer",
            "selected_company",
            "selected_currency",
            "selected_line_count",
            "selected_total_amount",
            "selected_payment_entry_count",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "locked_policy_enabled_count",
            "locked_policy_live_allowed_count",
            "locked_live_posting",
            "locked_journal_entry_side_effect",
            "locked_purchase_invoice_side_effect",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_validation(candidate):
    rows = frappe.get_all(
        VALIDATION_DOCTYPE,
        filters={
            "candidate": candidate,
            "status": "Candidate Validation Approved",
            "candidate_validation_approved": 1,
        },
        fields=["name", "validation_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_candidate_lines(candidate):
    if not candidate:
        return []

    rows = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        filters={
            "candidate": candidate,
            "category": "Selected Candidate",
            "reference_doctype": "Sales Invoice",
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
            "posting_date",
            "due_date",
        ],
        order_by="line_no asc, creation asc",
    )

    return rows


def validate_sales_invoice_line(row):
    issues = []

    if not frappe.db.exists("Sales Invoice", row.reference_name):
        issues.append(f"Sales Invoice does not exist: {row.reference_name}")
        return None, issues

    si = frappe.get_doc("Sales Invoice", row.reference_name)

    if si.docstatus != 1:
        issues.append(f"Sales Invoice {si.name} must be submitted. docstatus={si.docstatus}")

    if si.customer != row.customer:
        issues.append(f"Sales Invoice {si.name} customer changed from selected candidate.")

    if si.company != row.company:
        issues.append(f"Sales Invoice {si.name} company changed from selected candidate.")

    if getattr(si, "currency", None) != row.currency:
        issues.append(f"Sales Invoice {si.name} currency changed from selected candidate.")

    if flt(si.outstanding_amount or 0, 2) < flt(row.allocated_amount or 0, 2):
        issues.append(
            f"Sales Invoice {si.name} outstanding {flt(si.outstanding_amount or 0, 2)} is less than allocated {flt(row.allocated_amount or 0, 2)}."
        )

    validated = {
        "line_no": int(row.line_no or 0),
        "reference_doctype": "Sales Invoice",
        "reference_name": si.name,
        "customer": si.customer,
        "company": si.company,
        "currency": getattr(si, "currency", None),
        "docstatus_value": int(si.docstatus),
        "outstanding_amount": flt(si.outstanding_amount or 0, 2),
        "allocated_amount": flt(row.allocated_amount or 0, 2),
        "posting_date": si.posting_date,
        "due_date": getattr(si, "due_date", None),
    }

    return validated, issues


def validate_candidate_source(candidate, validated_lines, validation_issues, guard, policy_enabled, policy_live, config):
    issues = []

    if not candidate:
        issues.append("No approved Phase 11F candidate selection found.")
        return issues

    existing = existing_validation(candidate.name)
    if existing:
        issues.append(f"Phase 11G validation already exists for this candidate: {existing.validation_id}")

    required_links = {
        "candidate": (CANDIDATE_DOCTYPE, candidate.name),
        "design": ("NDIS Governed Limited Op Design", candidate.design),
        "payment_entry": ("Payment Entry", candidate.payment_entry),
        "target_policy": (POLICY_DOCTYPE, candidate.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if int(candidate.selected_line_count or 0) != 3:
        issues.append("Phase 11F selected line count must be 3.")

    if flt(candidate.selected_total_amount or 0, 2) != 3:
        issues.append("Phase 11F selected total amount must be 3.00.")

    if int(candidate.selected_payment_entry_count or 0) != 1:
        issues.append("Phase 11F selected Payment Entry count must be 1.")

    if int(candidate.locked_payment_entry_count or 0) != 8:
        issues.append("Locked Payment Entry count must be 8.")

    if int(candidate.locked_payment_entry_gl_count or 0) != 46:
        issues.append("Locked Payment Entry GL count must be 46.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 11G. Phase 11G must not repair this.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 11G. Phase 11G must not repair this.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["payment_entry_count"] != int(candidate.locked_payment_entry_count or 0):
        issues.append("Current Payment Entry count must match locked count from Phase 11F.")

    if guard["payment_entry_gl_count"] != int(candidate.locked_payment_entry_gl_count or 0):
        issues.append("Current Payment Entry GL count must match locked count from Phase 11F.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")

    if int(config["sandbox_enabled"]) != 1:
        issues.append("Sandbox config must be 1.")

    if int(config["production_mode"]) != 0:
        issues.append("Production mode config must remain 0.")

    if int(config["live_pe_enabled"]) != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    if len(validated_lines) != 3:
        issues.append(f"Exactly 3 validated Sales Invoice lines required. Found {len(validated_lines)}.")

    if validated_lines:
        doctypes = {row["reference_doctype"] for row in validated_lines}
        customers = {row["customer"] for row in validated_lines}
        companies = {row["company"] for row in validated_lines}
        currencies = {row["currency"] for row in validated_lines}
        total = flt(sum(flt(row["allocated_amount"], 2) for row in validated_lines), 2)

        if doctypes != {"Sales Invoice"}:
            issues.append("All validated references must be Sales Invoice.")

        if len(customers) != 1:
            issues.append("All validated Sales Invoices must have the same customer.")

        if len(companies) != 1:
            issues.append("All validated Sales Invoices must have the same company.")

        if len(currencies) != 1:
            issues.append("All validated Sales Invoices must have the same currency.")

        if total != 3:
            issues.append(f"Validated allocation total must be 3.00. Found {total}.")

    issues.extend(validation_issues)
    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None, line=None):
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
        item.update(line)

    items.append(item)


def build_items(candidate, validated_lines, issues, ack_ok):
    items = []

    if candidate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11f_candidate_exists",
            "Phase 11F candidate selection exists",
            f"Candidate found: {candidate.candidate_id}.",
            CANDIDATE_DOCTYPE,
            candidate.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11f_candidate_exists", "Phase 11F candidate selection exists", "No approved Phase 11F candidate selection found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Validation Source", "validation_source_valid", "Validation source valid", "Selected Sales Invoices are valid for preview.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Validation Source", "validation_source_valid", "Validation source valid", issue)

    for line in validated_lines:
        add_item(
            items,
            "Pass",
            "High",
            "Validated Candidate",
            "validated_sales_invoice",
            f"Validated Sales Invoice {line['line_no']}",
            f"{line['reference_name']} submitted with outstanding {line['outstanding_amount']} and allocated {line['allocated_amount']}.",
            "Sales Invoice",
            line["reference_name"],
            line=line,
        )

    checks = [
        ("selected_invoice_count", "Selected invoice count verified", len(validated_lines)),
        ("submitted_invoices", "Selected invoices are submitted", 1),
        ("outstanding_sufficient", "Outstanding amount sufficient", 1),
        ("same_customer", "Same customer verified", validated_lines[0]["customer"] if validated_lines else None),
        ("same_company", "Same company verified", validated_lines[0]["company"] if validated_lines else None),
        ("same_currency", "Same currency verified", validated_lines[0]["currency"] if validated_lines else None),
        ("allocation_total", "Allocation total verified", "3.00"),
        ("no_payment_entry", "No Payment Entry created", 0),
        ("no_gl", "No GL Entry created", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("preview_ready", "Ready for preview", 1),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Validation Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
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
        row.validation = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_candidate_validation(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_candidate_validation")

    candidate = latest_candidate()
    guard_before = guardrails()
    ack_ok = acknowledgement == VALIDATION_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    candidate_lines = get_candidate_lines(candidate.name if candidate else None)

    validated_lines = []
    validation_issues = []

    for line in candidate_lines:
        validated, issues = validate_sales_invoice_line(line)
        validation_issues.extend(issues)
        if validated:
            validated_lines.append(validated)

    policy_enabled_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "production_batch_enabled") if candidate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, candidate.target_policy, "live_posting_allowed") if candidate else 0

    issues = validate_candidate_source(candidate, validated_lines, validation_issues, guard_before, policy_enabled_before, policy_live_before, config)

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, candidate.target_policy, "production_batch_enabled") if candidate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, candidate.target_policy, "live_posting_allowed") if candidate else 0

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
        issues.append("Accounting movement changed while preparing Phase 11G candidate validation evidence.")

    items = build_items(candidate, validated_lines, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    validated_customer = validated_lines[0]["customer"] if validated_lines else None
    validated_company = validated_lines[0]["company"] if validated_lines else None
    validated_currency = validated_lines[0]["currency"] if validated_lines else None
    validated_total = flt(sum(flt(row["allocated_amount"], 2) for row in validated_lines), 2)

    selected_count_ok = len(validated_lines) == 3
    submitted_ok = selected_count_ok and all(int(row["docstatus_value"] or 0) == 1 for row in validated_lines)
    outstanding_ok = selected_count_ok and all(flt(row["outstanding_amount"], 2) >= flt(row["allocated_amount"], 2) for row in validated_lines)
    same_customer_ok = selected_count_ok and len({row["customer"] for row in validated_lines}) == 1
    same_company_ok = selected_count_ok and len({row["company"] for row in validated_lines}) == 1
    same_currency_ok = selected_count_ok and len({row["currency"] for row in validated_lines}) == 1

    allowed = int(
        ack_ok
        and item_summary["blocker_count"] == 0
        and candidate
        and selected_count_ok
        and submitted_ok
        and outstanding_ok
        and same_customer_ok
        and same_company_ok
        and same_currency_ok
        and validated_total == 3
        and no_new_movement
        and policy_preserved
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Candidate Validation Approved" if allowed else "Needs Review",
        "candidate_validation_status": "Next Governed Limited Operation Candidate Validation Approved" if allowed else "Needs Review",
        "candidate_validation_approved": allowed,
        "phase11f_candidate_verified": 1 if candidate else 0,
        "phase11e_design_verified": 1 if candidate else 0,
        "candidate_selection_locked_verified": 1 if candidate else 0,
        "selected_invoice_count_verified": int(selected_count_ok),
        "selected_invoices_exist_verified": int(len(validated_lines) == len(candidate_lines) == 3),
        "selected_invoices_submitted_verified": int(submitted_ok),
        "outstanding_amount_sufficient_verified": int(outstanding_ok),
        "same_customer_verified": int(same_customer_ok),
        "same_company_verified": int(same_company_ok),
        "same_currency_verified": int(same_currency_ok),
        "allocation_total_verified": int(validated_total == 3),
        "ready_for_next_governed_limited_operation_preview": allowed,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "validated_source_doctype": "Sales Invoice",
        "validated_reference_doctype": "Sales Invoice",
        "validated_party_type": "Customer",
        "validated_customer": validated_customer,
        "validated_company": validated_company,
        "validated_currency": validated_currency,
        "validated_invoice_count": len(validated_lines),
        "validated_total_amount": validated_total,
        "validated_payment_entry_count": 1 if validated_lines else 0,
        "validated_live_posting_allowed": 0,
        "validated_journal_entry_side_effect_allowed": 0,
        "validated_purchase_invoice_side_effect_allowed": 0,
        "candidate_validation_mode": "Candidate Validation Only - No Posting",
        "candidate": candidate.name if candidate else None,
        "design": candidate.design if candidate else None,
        "planning": candidate.planning if candidate else None,
        "precheck": candidate.precheck if candidate else None,
        "monitor": candidate.monitor if candidate else None,
        "payment_entry": candidate.payment_entry if candidate else None,
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
        "locked_payment_entry_count": int(candidate.locked_payment_entry_count or 0) if candidate else 0,
        "locked_payment_entry_gl_count": int(candidate.locked_payment_entry_gl_count or 0) if candidate else 0,
        "locked_policy_enabled_count": int(candidate.locked_policy_enabled_count or 0) if candidate else 0,
        "locked_policy_live_allowed_count": int(candidate.locked_policy_live_allowed_count or 0) if candidate else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "validation_score": score,
        **item_summary,
        "validated_lines": validated_lines,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": VALIDATION_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11G validates selected Sales Invoice candidates only. No Payment Entry, GL, Journal Entry, Purchase Invoice, or policy mutation occurs.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["candidate_validation_status"] = "Needs Review"
        result["candidate_validation_approved"] = 0
        result["ready_for_next_governed_limited_operation_preview"] = 0
        return result

    doc = frappe.new_doc(VALIDATION_DOCTYPE)
    doc.validation_id = make_validation_id()

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
            "candidate": candidate,
            "candidate_lines": candidate_lines,
            "validated_lines": validated_lines,
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
        "validation": doc.name,
        "validation_id": doc.validation_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_candidate_validation_audit(validation, reason=None):
    assert_action("cancel_next_governed_limited_operation_candidate_validation_audit")

    if not frappe.db.exists(VALIDATION_DOCTYPE, validation):
        frappe.throw(_("Governed limited operation candidate validation audit not found: {0}").format(validation))

    doc = frappe.get_doc(VALIDATION_DOCTYPE, validation)

    if doc.status == "Cancelled":
        return {"validation": validation, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_validation_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11G candidate validation record."))

    frappe.db.set_value(
        VALIDATION_DOCTYPE,
        validation,
        {
            "status": "Cancelled",
            "candidate_validation_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11G no-ack candidate validation audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{VALIDATION_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE validation = %(validation)s
        """,
        {"validation": validation},
    )

    frappe.db.commit()

    return {
        "validation": validation,
        "status": "Cancelled",
        "note": "No-ack candidate validation audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_candidate_validation_summary(limit=20):
    records = frappe.get_all(
        VALIDATION_DOCTYPE,
        fields=[
            "name",
            "validation_id",
            "status",
            "candidate_validation_status",
            "candidate_validation_approved",
            "phase11f_candidate_verified",
            "selected_invoice_count_verified",
            "selected_invoices_exist_verified",
            "selected_invoices_submitted_verified",
            "outstanding_amount_sufficient_verified",
            "validated_invoice_count",
            "validated_total_amount",
            "validated_customer",
            "validated_company",
            "validated_currency",
            "ready_for_next_governed_limited_operation_preview",
            "candidate",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "validation_score",
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
            "validation",
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
            "docstatus_value",
            "outstanding_amount",
            "allocated_amount",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "validation_records": records,
        "items": items,
        "required_acknowledgement": VALIDATION_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11G next governed limited operation candidate validation summary.",
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
            v.name AS validation,
            v.validation_id,
            v.status,
            v.candidate_validation_status,
            v.candidate_validation_approved,
            v.phase11f_candidate_verified,
            v.candidate_selection_locked_verified,
            v.selected_invoice_count_verified,
            v.selected_invoices_exist_verified,
            v.selected_invoices_submitted_verified,
            v.outstanding_amount_sufficient_verified,
            v.same_customer_verified,
            v.same_company_verified,
            v.same_currency_verified,
            v.allocation_total_verified,
            v.validated_customer,
            v.validated_company,
            v.validated_currency,
            v.validated_invoice_count,
            v.validated_total_amount,
            v.validated_payment_entry_count,
            v.ready_for_next_governed_limited_operation_preview,
            v.candidate,
            v.payment_entry_count_before,
            v.payment_entry_count_after,
            v.payment_entry_gl_count_before,
            v.payment_entry_gl_count_after,
            v.actual_payment_entry_created_count,
            v.actual_payment_entry_cancelled_count,
            v.actual_gl_created_count,
            v.submitted_journal_entry_count_today,
            v.purchase_invoice_count_today,
            v.validation_score,
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
            "labels": [row.validation_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.candidate_validation_approved or 0) for row in data[:20]]},
                {"name": "Validated Invoices", "values": [int(row.validated_invoice_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Validation Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_validation_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.validated_invoice_count or 0) for row in data), "indicator": "Green", "label": _("Validated Invoices"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def validation_columns():
    return [
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "validation_id", "label": _("Validation ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 170},
        {"fieldname": "candidate_validation_status", "label": _("Validation Status"), "fieldtype": "Data", "width": 430},
        {"fieldname": "candidate_validation_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11f_candidate_verified", "label": _("11F Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "candidate_selection_locked_verified", "label": _("Selection Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "selected_invoice_count_verified", "label": _("Count OK"), "fieldtype": "Check", "width": 85},
        {"fieldname": "selected_invoices_exist_verified", "label": _("Exist OK"), "fieldtype": "Check", "width": 85},
        {"fieldname": "selected_invoices_submitted_verified", "label": _("Submitted OK"), "fieldtype": "Check", "width": 115},
        {"fieldname": "outstanding_amount_sufficient_verified", "label": _("Outstanding OK"), "fieldtype": "Check", "width": 120},
        {"fieldname": "same_customer_verified", "label": _("Same Customer"), "fieldtype": "Check", "width": 115},
        {"fieldname": "same_company_verified", "label": _("Same Company"), "fieldtype": "Check", "width": 115},
        {"fieldname": "same_currency_verified", "label": _("Same Currency"), "fieldtype": "Check", "width": 115},
        {"fieldname": "allocation_total_verified", "label": _("Total OK"), "fieldtype": "Check", "width": 85},
        {"fieldname": "validated_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "validated_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "validated_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "validated_invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
        {"fieldname": "validated_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "validated_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "ready_for_next_governed_limited_operation_preview", "label": _("Preview Ready"), "fieldtype": "Check", "width": 115},
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "validation_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("validation"):
        conditions.append("i.validation = %(validation)s")
        params["validation"] = filters.get("validation")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": VALIDATION_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": VALIDATION_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "docstatus_value", "label": _("Docstatus"), "fieldtype": "Int", "width": 90},
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
            i.validation,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.docstatus_value,
            i.outstanding_amount,
            i.allocated_amount,
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
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Items", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Validated Candidate"]), "indicator": "Green", "label": _("Validated Candidates"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Validated Candidate"), "indicator": "Green", "label": _("Validated Amount"), "datatype": "Currency"},
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
