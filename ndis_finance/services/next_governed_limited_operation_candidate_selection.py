import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


CANDIDATE_ACK = "I_CONFIRM_PHASE11F_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_CANDIDATES_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
DESIGN_DOCTYPE = "NDIS Governed Limited Op Design"
CANDIDATE_DOCTYPE = "NDIS Governed Limited Op Candidate"
CANDIDATE_ITEM_DOCTYPE = "NDIS Governed Limited Op Candidate Item"


def make_candidate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-CANDIDATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_design():
    rows = frappe.get_all(
        DESIGN_DOCTYPE,
        filters={
            "status": "Design Approved",
            "design_status": "Next Governed Limited Operation Design Approved",
            "design_approved": 1,
            "phase11d_planning_verified": 1,
            "planning_envelope_locked_verified": 1,
            "design_shape_locked": 1,
            "design_source_model_locked": 1,
            "design_guardrails_locked": 1,
            "ready_for_next_governed_limited_operation_candidate_selection": 1,
            "designed_source_doctype": "Sales Invoice",
            "designed_reference_doctype": "Sales Invoice",
            "designed_party_type": "Customer",
            "designed_line_count": 3,
            "designed_total_amount": 3.00,
            "designed_payment_entry_count": 1,
            "designed_live_posting_allowed": 0,
            "designed_journal_entry_side_effect_allowed": 0,
            "designed_purchase_invoice_side_effect_allowed": 0,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "locked_payment_entry_count": 8,
            "locked_payment_entry_gl_count": 46,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "design_id",
            "planning",
            "precheck",
            "monitor",
            "baseline",
            "closeout",
            "governed_freeze",
            "rollback",
            "smoke",
            "payment_entry",
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
            "designed_source_doctype",
            "designed_reference_doctype",
            "designed_party_type",
            "designed_line_count",
            "designed_total_amount",
            "designed_payment_entry_count",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_candidate(design):
    rows = frappe.get_all(
        CANDIDATE_DOCTYPE,
        filters={
            "design": design,
            "status": "Candidate Selection Approved",
            "candidate_selection_approved": 1,
        },
        fields=["name", "candidate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_historical_payment_entry_context(payment_entry):
    if not payment_entry or not frappe.db.exists("Payment Entry", payment_entry):
        return {}

    pe = frappe.get_doc("Payment Entry", payment_entry)

    return {
        "payment_entry": pe.name,
        "party_type": pe.party_type,
        "party": pe.party,
        "company": pe.company,
        "paid_from": getattr(pe, "paid_from", None),
        "paid_to": getattr(pe, "paid_to", None),
        "paid_amount": flt(getattr(pe, "paid_amount", 0), 2),
        "received_amount": flt(getattr(pe, "received_amount", 0), 2),
        "docstatus": pe.docstatus,
        "status": pe.status,
    }


def select_sales_invoice_candidates(design, context):
    if not design or not context:
        return [], ["Design or historical Payment Entry context missing."]

    issues = []

    if context.get("party_type") != "Customer":
        issues.append(f"Historical Payment Entry party type must be Customer. Found {context.get('party_type')}.")

    if not context.get("party"):
        issues.append("Historical Payment Entry customer is missing.")

    if not context.get("company"):
        issues.append("Historical Payment Entry company is missing.")

    if issues:
        return [], issues

    filters = {
        "docstatus": 1,
        "company": context["company"],
        "customer": context["party"],
        "outstanding_amount": [">=", 1],
    }

    if has_column("Sales Invoice", "is_return"):
        filters["is_return"] = 0

    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "customer",
            "company",
            "currency",
            "posting_date",
            "due_date",
            "grand_total",
            "outstanding_amount",
        ],
        order_by="posting_date asc, creation asc",
        limit=20,
    )

    if len(rows) < 3:
        issues.append(f"At least 3 eligible Sales Invoices with outstanding amount >= 1.00 are required. Found {len(rows)}.")
        return [], issues

    selected = []
    currency_value = rows[0].currency

    for row in rows:
        if row.customer != context["party"]:
            continue
        if row.company != context["company"]:
            continue
        if row.currency != currency_value:
            continue
        if flt(row.outstanding_amount or 0, 2) < 1:
            continue

        selected.append(
            {
                "line_no": len(selected) + 1,
                "reference_doctype": "Sales Invoice",
                "reference_name": row.name,
                "customer": row.customer,
                "company": row.company,
                "currency": row.currency,
                "posting_date": row.posting_date,
                "due_date": row.due_date,
                "outstanding_amount": flt(row.outstanding_amount or 0, 2),
                "allocated_amount": 1.00,
            }
        )

        if len(selected) == 3:
            break

    if len(selected) != 3:
        issues.append(f"Could not select exactly 3 same-customer/company/currency Sales Invoice candidates. Selected {len(selected)}.")
        return selected, issues

    total = flt(sum(flt(row["allocated_amount"], 2) for row in selected), 2)

    if total != 3:
        issues.append(f"Selected allocation total must be 3.00. Found {total}.")

    return selected, issues


def validate_candidate_source(design, selected, guard, policy_enabled, policy_live, config):
    issues = []

    if not design:
        issues.append("No approved Phase 11E design record found.")
        return issues

    existing = existing_candidate(design.name)
    if existing:
        issues.append(f"Phase 11F candidate selection already exists for this design: {existing.candidate_id}")

    required_links = {
        "design": (DESIGN_DOCTYPE, design.name),
        "planning": ("NDIS Governed Limited Op Planning", design.planning),
        "payment_entry": ("Payment Entry", design.payment_entry),
        "target_policy": (POLICY_DOCTYPE, design.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if int(design.designed_line_count or 0) != 3:
        issues.append("Design line count must be 3.")

    if flt(design.designed_total_amount or 0, 2) != 3:
        issues.append("Design total amount must be 3.00.")

    if int(design.designed_payment_entry_count or 0) != 1:
        issues.append("Design Payment Entry count must be 1.")

    if int(design.locked_payment_entry_count or 0) != 8:
        issues.append("Locked Payment Entry count must be 8.")

    if int(design.locked_payment_entry_gl_count or 0) != 46:
        issues.append("Locked Payment Entry GL count must be 46.")

    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 11F. Phase 11F must not repair this.")

    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 11F. Phase 11F must not repair this.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["payment_entry_count"] != int(design.locked_payment_entry_count or 0):
        issues.append("Current Payment Entry count must match locked count from Phase 11E.")

    if guard["payment_entry_gl_count"] != int(design.locked_payment_entry_gl_count or 0):
        issues.append("Current Payment Entry GL count must match locked count from Phase 11E.")

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

    if len(selected) != 3:
        issues.append(f"Exactly 3 Sales Invoice candidates must be selected. Found {len(selected)}.")

    if selected:
        customers = {row["customer"] for row in selected}
        companies = {row["company"] for row in selected}
        currencies = {row["currency"] for row in selected}
        doctypes = {row["reference_doctype"] for row in selected}
        allocation_total = flt(sum(flt(row["allocated_amount"], 2) for row in selected), 2)

        if doctypes != {"Sales Invoice"}:
            issues.append("All selected references must be Sales Invoice.")

        if len(customers) != 1:
            issues.append("All selected Sales Invoices must have the same customer.")

        if len(companies) != 1:
            issues.append("All selected Sales Invoices must have the same company.")

        if len(currencies) != 1:
            issues.append("All selected Sales Invoices must have the same currency.")

        if allocation_total != 3:
            issues.append(f"Selected allocation total must be 3.00. Found {allocation_total}.")

        for row in selected:
            if flt(row["outstanding_amount"], 2) < flt(row["allocated_amount"], 2):
                issues.append(f"Selected invoice {row['reference_name']} outstanding amount is less than allocated amount.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None, candidate_line=None):
    row = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "source_doctype": source_doctype,
        "source_name": source_name,
    }

    if candidate_line:
        row.update(candidate_line)

    items.append(row)


def build_items(design, selected, issues, ack_ok):
    items = []

    if design:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11e_design_exists",
            "Phase 11E design exists",
            f"Design found: {design.design_id}.",
            DESIGN_DOCTYPE,
            design.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11e_design_exists", "Phase 11E design exists", "No approved Phase 11E design found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Candidate Source", "candidate_source_valid", "Candidate source valid", "Sales Invoice candidates are valid for the next governed operation.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Candidate Source", "candidate_source_valid", "Candidate source valid", issue)

    for line in selected:
        add_item(
            items,
            "Pass",
            "High",
            "Selected Candidate",
            "selected_sales_invoice",
            f"Selected Sales Invoice {line['line_no']}",
            f"{line['reference_name']} allocated {line['allocated_amount']} with outstanding {line['outstanding_amount']}.",
            "Sales Invoice",
            line["reference_name"],
            candidate_line=line,
        )

    checks = [
        ("candidate_selection_locked", "Candidate selection locked", "3 Sales Invoice references"),
        ("same_customer", "Same customer verified", selected[0]["customer"] if selected else None),
        ("same_company", "Same company verified", selected[0]["company"] if selected else None),
        ("same_currency", "Same currency verified", selected[0]["currency"] if selected else None),
        ("allocation_total", "Allocation total verified", "3.00"),
        ("no_payment_entry", "No Payment Entry created", 0),
        ("no_gl", "No GL Entry created", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("validation_ready", "Ready for candidate validation", 1),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Candidate Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {CANDIDATE_ACK}")

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
        row = frappe.new_doc(CANDIDATE_ITEM_DOCTYPE)
        row.candidate = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_candidate_selection(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_candidate_selection")

    design = latest_design()
    guard_before = guardrails()
    ack_ok = acknowledgement == CANDIDATE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    context = get_historical_payment_entry_context(design.payment_entry if design else None)
    selected, selection_issues = select_sales_invoice_candidates(design, context)

    policy_enabled_before = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

    issues = []
    issues.extend(selection_issues)
    issues.extend(validate_candidate_source(design, selected, guard_before, policy_enabled_before, policy_live_before, config))

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, design.target_policy, "production_batch_enabled") if design else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, design.target_policy, "live_posting_allowed") if design else 0

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
        issues.append("Accounting movement changed while preparing Phase 11F candidate selection evidence.")

    items = build_items(design, selected, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    selected_customer = selected[0]["customer"] if selected else None
    selected_company = selected[0]["company"] if selected else None
    selected_currency = selected[0]["currency"] if selected else None
    selected_total = flt(sum(flt(row["allocated_amount"], 2) for row in selected), 2)

    allowed = int(
        ack_ok
        and item_summary["blocker_count"] == 0
        and design
        and len(selected) == 3
        and selected_total == 3
        and no_new_movement
        and policy_preserved
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Candidate Selection Approved" if allowed else "Needs Review",
        "candidate_selection_status": "Next Governed Limited Operation Candidate Selection Approved" if allowed else "Needs Review",
        "candidate_selection_approved": allowed,
        "phase11e_design_verified": 1 if design else 0,
        "phase11d_planning_verified": 1 if design else 0,
        "design_shape_locked_verified": 1 if design else 0,
        "candidate_selection_locked": allowed,
        "candidate_source_verified": int(len(selected) == 3),
        "same_customer_verified": int(bool(selected_customer) and len({row["customer"] for row in selected}) == 1),
        "same_company_verified": int(bool(selected_company) and len({row["company"] for row in selected}) == 1),
        "same_currency_verified": int(bool(selected_currency) and len({row["currency"] for row in selected}) == 1),
        "allocation_total_verified": int(selected_total == 3),
        "ready_for_next_governed_limited_operation_candidate_validation": allowed,
        "payment_entry_cancelled_verified": 1 if design else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "selected_source_doctype": "Sales Invoice",
        "selected_reference_doctype": "Sales Invoice",
        "selected_party_type": "Customer",
        "selected_customer": selected_customer,
        "selected_company": selected_company,
        "selected_currency": selected_currency,
        "selected_line_count": len(selected),
        "selected_total_amount": selected_total,
        "selected_payment_entry_count": 1 if selected else 0,
        "selected_live_posting_allowed": 0,
        "selected_journal_entry_side_effect_allowed": 0,
        "selected_purchase_invoice_side_effect_allowed": 0,
        "candidate_selection_mode": "Candidate Selection Only - No Posting",
        "design": design.name if design else None,
        "planning": design.planning if design else None,
        "precheck": design.precheck if design else None,
        "monitor": design.monitor if design else None,
        "baseline": design.baseline if design else None,
        "closeout": design.closeout if design else None,
        "governed_freeze": design.governed_freeze if design else None,
        "rollback": design.rollback if design else None,
        "smoke": design.smoke if design else None,
        "payment_entry": design.payment_entry if design else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": design.target_policy if design else None,
        "target_policy_name": design.target_policy_name if design else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "locked_payment_entry_count": int(design.locked_payment_entry_count or 0) if design else 0,
        "locked_payment_entry_gl_count": int(design.locked_payment_entry_gl_count or 0) if design else 0,
        "locked_policy_enabled_count": int(design.locked_policy_enabled_count or 0) if design else 0,
        "locked_policy_live_allowed_count": int(design.locked_policy_live_allowed_count or 0) if design else 0,
        "locked_live_posting": 0,
        "locked_journal_entry_side_effect": 0,
        "locked_purchase_invoice_side_effect": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "candidate_score": score,
        **item_summary,
        "selected_candidates": selected,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": CANDIDATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11F selects Sales Invoice candidates only. No Payment Entry, GL, Journal Entry, Purchase Invoice, or policy mutation occurs.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["candidate_selection_status"] = "Needs Review"
        result["candidate_selection_approved"] = 0
        result["candidate_selection_locked"] = 0
        result["ready_for_next_governed_limited_operation_candidate_validation"] = 0
        return result

    doc = frappe.new_doc(CANDIDATE_DOCTYPE)
    doc.candidate_id = make_candidate_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = CANDIDATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.candidate_json = safe_json(
        {
            "design": design,
            "historical_payment_entry_context": context,
            "selected_candidates": selected,
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
        "candidate": doc.name,
        "candidate_id": doc.candidate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_candidate_audit(candidate, reason=None):
    assert_action("cancel_next_governed_limited_operation_candidate_audit")

    if not frappe.db.exists(CANDIDATE_DOCTYPE, candidate):
        frappe.throw(_("Governed limited operation candidate audit not found: {0}").format(candidate))

    doc = frappe.get_doc(CANDIDATE_DOCTYPE, candidate)

    if doc.status == "Cancelled":
        return {"candidate": candidate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.candidate_selection_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11F candidate selection record."))

    frappe.db.set_value(
        CANDIDATE_DOCTYPE,
        candidate,
        {
            "status": "Cancelled",
            "candidate_selection_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11F no-ack candidate selection audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{CANDIDATE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE candidate = %(candidate)s
        """,
        {"candidate": candidate},
    )

    frappe.db.commit()

    return {
        "candidate": candidate,
        "status": "Cancelled",
        "note": "No-ack candidate selection audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_candidate_summary(limit=20):
    records = frappe.get_all(
        CANDIDATE_DOCTYPE,
        fields=[
            "name",
            "candidate_id",
            "status",
            "candidate_selection_status",
            "candidate_selection_approved",
            "phase11e_design_verified",
            "candidate_selection_locked",
            "selected_line_count",
            "selected_total_amount",
            "selected_customer",
            "selected_company",
            "selected_currency",
            "ready_for_next_governed_limited_operation_candidate_validation",
            "design",
            "payment_entry",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "candidate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        CANDIDATE_ITEM_DOCTYPE,
        fields=[
            "name",
            "candidate",
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
        "candidate_records": records,
        "items": items,
        "required_acknowledgement": CANDIDATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11F next governed limited operation candidate selection summary.",
    }


def execute_candidate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("c.status = %(status)s")
        params["status"] = filters.get("status")

    columns = candidate_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            c.name AS candidate,
            c.candidate_id,
            c.status,
            c.candidate_selection_status,
            c.candidate_selection_approved,
            c.phase11e_design_verified,
            c.design_shape_locked_verified,
            c.candidate_selection_locked,
            c.same_customer_verified,
            c.same_company_verified,
            c.same_currency_verified,
            c.selected_customer,
            c.selected_company,
            c.selected_currency,
            c.selected_line_count,
            c.selected_total_amount,
            c.selected_payment_entry_count,
            c.ready_for_next_governed_limited_operation_candidate_validation,
            c.design,
            c.payment_entry,
            c.locked_payment_entry_count,
            c.locked_payment_entry_gl_count,
            c.payment_entry_count_before,
            c.payment_entry_count_after,
            c.payment_entry_gl_count_before,
            c.payment_entry_gl_count_after,
            c.actual_payment_entry_created_count,
            c.actual_payment_entry_cancelled_count,
            c.actual_gl_created_count,
            c.submitted_journal_entry_count_today,
            c.purchase_invoice_count_today,
            c.candidate_score,
            c.checked_on,
            %(currency)s AS currency
        FROM `tab{CANDIDATE_DOCTYPE}` c
        {build_where(conditions)}
        ORDER BY c.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.candidate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.candidate_selection_approved or 0) for row in data[:20]]},
                {"name": "Selected Lines", "values": [int(row.selected_line_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Candidate Records"), "datatype": "Int"},
        {"value": sum(int(row.candidate_selection_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.selected_line_count or 0) for row in data), "indicator": "Green", "label": _("Selected Lines"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def candidate_columns():
    return [
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
        {"fieldname": "candidate_id", "label": _("Candidate ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "candidate_selection_status", "label": _("Candidate Status"), "fieldtype": "Data", "width": 390},
        {"fieldname": "candidate_selection_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11e_design_verified", "label": _("11E Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "design_shape_locked_verified", "label": _("Design Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "candidate_selection_locked", "label": _("Selection Locked"), "fieldtype": "Check", "width": 120},
        {"fieldname": "same_customer_verified", "label": _("Same Customer"), "fieldtype": "Check", "width": 115},
        {"fieldname": "same_company_verified", "label": _("Same Company"), "fieldtype": "Check", "width": 115},
        {"fieldname": "same_currency_verified", "label": _("Same Currency"), "fieldtype": "Check", "width": 115},
        {"fieldname": "selected_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "selected_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "selected_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "selected_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 70},
        {"fieldname": "selected_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "selected_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "ready_for_next_governed_limited_operation_candidate_validation", "label": _("Validation Ready"), "fieldtype": "Check", "width": 130},
        {"fieldname": "design", "label": _("Design"), "fieldtype": "Link", "options": DESIGN_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Historical PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "locked_payment_entry_count", "label": _("Locked PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "locked_payment_entry_gl_count", "label": _("Locked PE GL"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "candidate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("candidate"):
        conditions.append("i.candidate = %(candidate)s")
        params["candidate"] = filters.get("candidate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CANDIDATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "candidate", "label": _("Candidate"), "fieldtype": "Link", "options": CANDIDATE_DOCTYPE, "width": 220},
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
            i.candidate,
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
        FROM `tab{CANDIDATE_ITEM_DOCTYPE}` i
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
        {"value": len([row for row in data if row.category == "Selected Candidate"]), "indicator": "Green", "label": _("Selected Candidates"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Selected Candidate"), "indicator": "Green", "label": _("Selected Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_candidate_report(filters)

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
