import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ONLY_CONFIRMATION = "PAYMENT_ENTRY_ALLOCATION_PREVIEW_ONLY_NO_PAYMENT_ENTRY"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-ALLOC-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def first_existing_value(doc, fieldnames, default=None):
    for fieldname in fieldnames:
        if doc.meta.has_field(fieldname):
            value = doc.get(fieldname)
            if value not in [None, ""]:
                return value
    return default


def latest_design_review():
    rows = frappe.get_all(
        "NDIS Accounting Design Review",
        filters={"design_approved_for_next_phase": 1, "status": ["in", ["Passed", "Needs Review"]]},
        fields=["name", "review_id", "status"],
        order_by="reviewed_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def latest_sandbox_completion_gate():
    rows = frappe.get_all(
        "NDIS Accounting Sandbox Completion Gate",
        filters={"sandbox_completion_allowed": 1, "status": ["in", ["Passed", "Needs Review"]]},
        fields=["name", "gate_id", "status", "completion_score"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def get_remittance_design_matrix():
    rows = frappe.get_all(
        "NDIS Accounting Design Matrix",
        filters={
            "event_type": "Remittance",
            "source_doctype": "NDIS Remittance Import",
            "design_status": ["in", ["Active", "Draft"]],
        },
        fields=[
            "name",
            "matrix_id",
            "design_status",
            "allowed_target_doctype",
            "payment_entry_allowed_later",
            "direct_gl_allowed",
            "requires_duplicate_check",
            "requires_reversal_plan",
        ],
        limit=1,
    )
    return rows[0] if rows else None


def get_mapping_rule(mapping_rule=None, payer_type=None):
    if mapping_rule:
        if not frappe.db.exists("NDIS Payment Entry Mapping Rule", mapping_rule):
            frappe.throw(_("Payment Entry Mapping Rule not found: {0}").format(mapping_rule))
        return frappe.get_doc("NDIS Payment Entry Mapping Rule", mapping_rule)

    filters = {"status": ["in", ["Active", "Draft"]], "remittance_source_doctype": "NDIS Remittance Import"}
    if payer_type:
        filters["payer_type"] = payer_type

    rows = frappe.get_all(
        "NDIS Payment Entry Mapping Rule",
        filters=filters,
        fields=["name", "status"],
        order_by="case when status='Active' then 0 else 1 end, modified desc",
        limit=1,
    )
    if not rows:
        frappe.throw(_("No Payment Entry Mapping Rule found."))
    return frappe.get_doc("NDIS Payment Entry Mapping Rule", rows[0].name)


def get_source_doc(remittance_import):
    if not frappe.db.exists("NDIS Remittance Import", remittance_import):
        frappe.throw(_("NDIS Remittance Import not found: {0}").format(remittance_import))
    return frappe.get_doc("NDIS Remittance Import", remittance_import)


def get_remittance_lines(remittance_import):
    rows = []
    if frappe.db.has_column("NDIS Remittance Import Line", "parent"):
        rows = frappe.get_all(
            "NDIS Remittance Import Line",
            filters={"parent": remittance_import},
            fields=["name"],
            order_by="idx asc, creation asc",
            limit=10000,
        )
    if not rows and frappe.get_meta("NDIS Remittance Import Line").has_field("remittance_import"):
        rows = frappe.get_all(
            "NDIS Remittance Import Line",
            filters={"remittance_import": remittance_import},
            fields=["name"],
            order_by="creation asc",
            limit=10000,
        )
    return [frappe.get_doc("NDIS Remittance Import Line", row.name) for row in rows]


def derive_company(source_doc, mapping_doc):
    return first_existing_value(source_doc, ["company"], None) or mapping_doc.company or frappe.defaults.get_user_default("Company")


def derive_source_status(source_doc):
    return first_existing_value(source_doc, ["status", "import_status", "workflow_state"], "")


def derive_source_summary(source_doc):
    parts = []
    status = derive_source_status(source_doc)
    if status:
        parts.append(f"Status: {status}")
    for fieldname in ["total_received_amount", "received_amount", "allocated_amount", "total_amount", "import_total", "line_count"]:
        if source_doc.meta.has_field(fieldname):
            value = source_doc.get(fieldname)
            if value not in [None, ""]:
                parts.append(f"{fieldname}: {value}")
    return "; ".join(parts)


def derive_line_amount(line_doc):
    return abs(flt(first_existing_value(line_doc, ["paid_amount", "received_amount", "allocated_amount", "payment_amount", "amount_paid", "amount", "claim_amount", "invoice_amount"], 0)))


def derive_line_outcome(line_doc):
    return str(first_existing_value(line_doc, ["outcome", "payment_outcome", "claim_outcome", "claim_status", "invoice_status", "status", "result"], "") or "")


def derive_sales_invoice(line_doc):
    for value in [
        first_existing_value(line_doc, ["sales_invoice", "invoice", "invoice_name", "sales_invoice_name"], None),
        first_existing_value(line_doc, ["reference_invoice", "erpnext_invoice"], None),
        first_existing_value(line_doc, ["invoice_number", "invoice_no", "invoice_reference"], None),
    ]:
        if value and frappe.db.exists("Sales Invoice", value):
            return value
    return None


def derive_claim_line(line_doc):
    return first_existing_value(line_doc, ["claim_line", "ndis_claim_line", "claim_batch_line", "matched_claim_line", "reconciliation_line"], None)


def get_invoice_info(sales_invoice):
    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        return {"invoice_status": "", "outstanding_amount": 0, "customer": None}
    row = frappe.db.get_value("Sales Invoice", sales_invoice, ["status", "outstanding_amount", "customer"], as_dict=True) or {}
    return {"invoice_status": row.get("status") or "", "outstanding_amount": flt(row.get("outstanding_amount")), "customer": row.get("customer")}


def make_duplicate_key(remittance_import, line_doc, sales_invoice, amount):
    return "|".join([str(remittance_import or ""), str(line_doc.name or ""), str(sales_invoice or ""), str(round(flt(amount), 2))])


def duplicate_exists(duplicate_key):
    if not duplicate_key:
        return False
    return bool(frappe.db.count("NDIS Payment Entry Allocation Preview Line", {"duplicate_key": duplicate_key, "status": ["!=", "Cancelled"]}))


def evaluate_line(remittance_import, line_doc, mapping_doc):
    amount = derive_line_amount(line_doc)
    outcome = derive_line_outcome(line_doc)
    outcome_lower = outcome.lower()
    sales_invoice = derive_sales_invoice(line_doc)
    claim_line = derive_claim_line(line_doc)
    invoice_info = get_invoice_info(sales_invoice)
    duplicate_key = make_duplicate_key(remittance_import, line_doc, sales_invoice, amount)
    duplicate_detected = duplicate_exists(duplicate_key)

    status = "Exception"
    decision = "Manual Review"
    block_reason = ""
    recommendation = "Review manually before any future Payment Entry adapter."
    allocation_amount = 0
    exception_amount = amount

    if duplicate_detected:
        status = "Duplicate"
        decision = "Duplicate Detected"
        block_reason = "Duplicate allocation preview key already exists."
        recommendation = "Review previous preview lines before future Payment Entry creation."
    elif "reject" in outcome_lower:
        status = "Excluded"
        decision = "Rejected Claim Excluded"
        block_reason = "Rejected remittance line must not be allocated to Payment Entry."
        recommendation = mapping_doc.rejected_handling or "Route to leakage/recovery."
    elif "short" in outcome_lower or "partial" in outcome_lower:
        status = "Exception"
        decision = "Short Paid / Partial Payment"
        block_reason = "Short-paid remittance line needs leakage/recovery treatment before allocation."
        recommendation = mapping_doc.short_paid_handling or "Route to leakage/recovery."
        allocation_amount = amount if mapping_doc.short_paid_handling == "Allow Partial Allocation Later" else 0
        exception_amount = amount - allocation_amount
    elif not sales_invoice:
        status = "Exception"
        decision = "Unmatched Invoice"
        block_reason = "No Sales Invoice could be matched."
        recommendation = "Resolve invoice matching before future Payment Entry creation."
    elif invoice_info["outstanding_amount"] <= 0:
        status = "Exception"
        decision = "Invoice Not Outstanding"
        block_reason = "Matched invoice has no outstanding amount."
        recommendation = "Do not allocate receipt to fully paid or closed invoice."
    elif amount > invoice_info["outstanding_amount"]:
        status = "Exception"
        decision = "Overpayment / Amount Exceeds Outstanding"
        block_reason = "Receipt amount exceeds invoice outstanding amount."
        recommendation = mapping_doc.overpayment_handling or "Hold overpayment as exception."
        allocation_amount = invoice_info["outstanding_amount"]
        exception_amount = amount - allocation_amount
    else:
        status = "Allocatable"
        decision = "Future Payment Entry Allocation Candidate"
        recommendation = "Eligible for future sandbox Payment Entry adapter only after Phase 3C."
        allocation_amount = amount
        exception_amount = 0

    return frappe._dict(
        {
            "status": status,
            "line_label": first_existing_value(line_doc, ["line_label", "invoice_number", "invoice_no", "claim_reference"], line_doc.name),
            "remittance_line": line_doc.name,
            "claim_line": claim_line,
            "sales_invoice": sales_invoice,
            "invoice_status": invoice_info["invoice_status"],
            "receipt_amount": amount,
            "invoice_outstanding_amount": invoice_info["outstanding_amount"],
            "allocation_amount": allocation_amount,
            "exception_amount": exception_amount,
            "outcome_status": outcome,
            "allocation_decision": decision,
            "duplicate_key": duplicate_key,
            "duplicate_detected": int(duplicate_detected),
            "block_reason": block_reason,
            "recommendation": recommendation,
            "future_payment_entry_reference": "",
            "preview_only_note": "Preview only. No Payment Entry created.",
        }
    )


def validate_mapping(mapping_doc):
    items = []
    if mapping_doc.status != "Active":
        items.append({"status": "Warning", "label": "Mapping rule is not Active", "detail": f"Mapping rule status is {mapping_doc.status}. Preview can run, but future adapter should require Active mapping."})
    if int(mapping_doc.payment_entry_creation_allowed or 0):
        items.append({"status": "Blocker", "label": "Payment Entry creation flag is enabled", "detail": "Phase 3B must not allow Payment Entry creation."})
    if int(mapping_doc.requires_bank_account_mapping or 0) and not mapping_doc.bank_account:
        items.append({"status": "Warning", "label": "Bank account not mapped", "detail": "Future Payment Entry adapter will require a bank account mapping."})
    if int(mapping_doc.requires_receivable_account_mapping or 0) and not mapping_doc.receivable_account:
        items.append({"status": "Warning", "label": "Receivable account not mapped", "detail": "Future Payment Entry adapter will require a receivable account mapping."})
    if int(mapping_doc.requires_rollback_plan or 0) and not mapping_doc.rollback_rule:
        items.append({"status": "Warning", "label": "Rollback rule missing", "detail": "Future Payment Entry adapter requires rollback/cancel design."})
    return items


def validate_design_gates():
    items = []
    design_review = latest_design_review()
    sandbox_gate = latest_sandbox_completion_gate()
    matrix = get_remittance_design_matrix()

    if not design_review:
        items.append({"status": "Blocker", "label": "No approved Phase 3A design review", "detail": "Phase 3B requires an approved controlled accounting design review."})
    if not sandbox_gate:
        items.append({"status": "Blocker", "label": "No allowed sandbox completion gate", "detail": "Phase 3B requires Phase 2F sandbox completion gate allowed."})
    if not matrix:
        items.append({"status": "Blocker", "label": "No remittance design matrix row", "detail": "Missing Remittance design matrix row for NDIS Remittance Import."})
    else:
        if matrix.allowed_target_doctype != "Payment Entry":
            items.append({"status": "Blocker", "label": "Remittance target is not Payment Entry", "detail": f"Design matrix target is {matrix.allowed_target_doctype}. Expected Payment Entry."})
        if int(matrix.direct_gl_allowed or 0):
            items.append({"status": "Blocker", "label": "Direct GL allowed in design matrix", "detail": "Direct GL must remain blocked."})
        if not int(matrix.payment_entry_allowed_later or 0):
            items.append({"status": "Warning", "label": "Payment Entry future flag not enabled", "detail": "Design matrix does not mark Payment Entry as allowed later."})
    return design_review, sandbox_gate, matrix, items


def summarise_preview(lines, validation_items):
    blocker_count = len([row for row in validation_items if row.get("status") == "Blocker"])
    warning_count = len([row for row in validation_items if row.get("status") == "Warning"])
    total_receipt = sum(flt(row.receipt_amount) for row in lines)
    allocatable_amount = sum(flt(row.allocation_amount) for row in lines if row.status == "Allocatable")
    exception_amount = sum(flt(row.exception_amount) for row in lines if row.status != "Allocatable")
    unmatched_amount = sum(flt(row.receipt_amount) for row in lines if row.allocation_decision == "Unmatched Invoice")
    allocatable_line_count = len([row for row in lines if row.status == "Allocatable"])
    exception_line_count = len([row for row in lines if row.status in ["Exception", "Excluded"]])
    duplicate_line_count = len([row for row in lines if row.status == "Duplicate"])
    warning_count += duplicate_line_count + exception_line_count

    if blocker_count:
        status = "Blocked"
        validation_status = "Blocked"
    elif warning_count:
        status = "Needs Review"
        validation_status = "Warning"
    else:
        status = "Previewed"
        validation_status = "Pass"

    return {
        "status": status,
        "validation_status": validation_status,
        "total_receipt_amount": total_receipt,
        "allocatable_amount": allocatable_amount,
        "exception_amount": exception_amount,
        "unmatched_amount": unmatched_amount,
        "line_count": len(lines),
        "allocatable_line_count": allocatable_line_count,
        "exception_line_count": exception_line_count,
        "duplicate_line_count": duplicate_line_count,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
    }


@frappe.whitelist()
def create_payment_entry_allocation_preview(remittance_import, mapping_rule=None, dry_run=0, notes=None):
    assert_action("run_payment_entry_allocation_preview")

    source_doc = get_source_doc(remittance_import)
    mapping_doc = get_mapping_rule(mapping_rule=mapping_rule)
    design_review, sandbox_gate, matrix, validation_items = validate_design_gates()
    validation_items.extend(validate_mapping(mapping_doc))

    company = derive_company(source_doc, mapping_doc)
    source_status = derive_source_status(source_doc)
    source_summary = derive_source_summary(source_doc)
    remittance_lines = get_remittance_lines(remittance_import)
    preview_lines = []

    if not remittance_lines:
        validation_items.append({"status": "Blocker", "label": "No remittance lines found", "detail": "Cannot build allocation preview without remittance import lines."})

    for line_doc in remittance_lines:
        preview_lines.append(evaluate_line(remittance_import, line_doc, mapping_doc))

    summary = summarise_preview(preview_lines, validation_items)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "remittance_import": remittance_import,
        "mapping_rule": mapping_doc.name,
        "mapping_status": mapping_doc.status,
        "design_review": design_review.name if design_review else None,
        "sandbox_completion_gate": sandbox_gate.name if sandbox_gate else None,
        "design_matrix": matrix.name if matrix else None,
        "status": summary["status"],
        "validation_status": summary["validation_status"],
        "summary": summary,
        "validation_items": validation_items,
        "preview_lines": preview_lines,
        "preview_only_confirmation": PREVIEW_ONLY_CONFIRMATION,
        "note": "Payment Entry allocation preview only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS Payment Entry Allocation Preview")
    doc.preview_id = make_preview_id()
    doc.status = summary["status"]
    doc.validation_status = summary["validation_status"]
    doc.mapping_rule = mapping_doc.name
    doc.remittance_import = remittance_import
    doc.source_status = source_status
    doc.source_summary = source_summary
    doc.sandbox_completion_gate = sandbox_gate.name if sandbox_gate else None
    doc.sandbox_completion_allowed = 1 if sandbox_gate else 0
    doc.design_review = design_review.name if design_review else None
    doc.design_approved = 1 if design_review else 0
    doc.payment_entry_creation_allowed = 0
    doc.preview_only_confirmation = PREVIEW_ONLY_CONFIRMATION
    doc.company = company
    doc.payer_type = mapping_doc.payer_type
    doc.payer_customer = mapping_doc.payer_customer
    doc.payment_type = mapping_doc.payment_type
    doc.mode_of_payment = mapping_doc.mode_of_payment
    doc.bank_account = mapping_doc.bank_account
    doc.receivable_account = mapping_doc.receivable_account
    doc.posting_date = today()
    doc.currency = currency()
    doc.total_receipt_amount = summary["total_receipt_amount"]
    doc.allocatable_amount = summary["allocatable_amount"]
    doc.exception_amount = summary["exception_amount"]
    doc.unmatched_amount = summary["unmatched_amount"]
    doc.line_count = summary["line_count"]
    doc.allocatable_line_count = summary["allocatable_line_count"]
    doc.exception_line_count = summary["exception_line_count"]
    doc.duplicate_line_count = summary["duplicate_line_count"]
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.created_on = now_datetime()
    doc.created_by_user = frappe.session.user
    doc.validation_log = safe_json(validation_items)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for idx, row in enumerate(preview_lines, start=1):
        line = frappe.new_doc("NDIS Payment Entry Allocation Preview Line")
        line.allocation_preview = doc.name
        line.status = row.status
        line.line_no = idx
        line.line_label = row.line_label
        line.remittance_line = row.remittance_line
        line.claim_line = row.claim_line
        line.sales_invoice = row.sales_invoice
        line.invoice_status = row.invoice_status
        line.receipt_amount = row.receipt_amount
        line.invoice_outstanding_amount = row.invoice_outstanding_amount
        line.allocation_amount = row.allocation_amount
        line.exception_amount = row.exception_amount
        line.outcome_status = row.outcome_status
        line.allocation_decision = row.allocation_decision
        line.duplicate_key = row.duplicate_key
        line.duplicate_detected = row.duplicate_detected
        line.block_reason = row.block_reason
        line.recommendation = row.recommendation
        line.future_payment_entry_reference = row.future_payment_entry_reference
        line.preview_only_note = row.preview_only_note
        line.insert(ignore_permissions=True)

    frappe.db.set_value(
        "NDIS Payment Entry Mapping Rule",
        mapping_doc.name,
        {
            "last_preview": doc.name,
            "last_preview_on": doc.created_on,
            "preview_count": frappe.db.count("NDIS Payment Entry Allocation Preview", {"mapping_rule": mapping_doc.name, "status": ["!=", "Cancelled"]}),
        },
        update_modified=False,
    )
    frappe.db.commit()

    result["created"] = True
    result["allocation_preview"] = doc.name
    result["preview_id"] = doc.preview_id
    return result


@frappe.whitelist()
def cancel_payment_entry_allocation_preview(allocation_preview, reason=None):
    assert_action("cancel_payment_entry_allocation_preview")
    if not frappe.db.exists("NDIS Payment Entry Allocation Preview", allocation_preview):
        frappe.throw(_("Payment Entry Allocation Preview not found: {0}").format(allocation_preview))
    frappe.db.set_value(
        "NDIS Payment Entry Allocation Preview",
        allocation_preview,
        {"status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "validation_log": reason or "Payment Entry allocation preview cancelled."},
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Payment Entry Allocation Preview Line`
        SET status = 'Cancelled'
        WHERE allocation_preview = %(allocation_preview)s
        """,
        {"allocation_preview": allocation_preview},
    )
    frappe.db.commit()
    return {"allocation_preview": allocation_preview, "status": "Cancelled", "note": "Allocation preview cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_payment_entry_design_summary(limit=20):
    mapping_rules = frappe.get_all(
        "NDIS Payment Entry Mapping Rule",
        fields=["name", "mapping_id", "mapping_name", "status", "company", "payer_type", "mapping_scope", "payment_type", "bank_account", "receivable_account", "payment_entry_creation_allowed", "preview_count", "last_preview_on"],
        order_by="mapping_id asc",
        limit=int(limit or 20),
    )
    previews = frappe.get_all(
        "NDIS Payment Entry Allocation Preview",
        fields=["name", "preview_id", "status", "validation_status", "mapping_rule", "remittance_import", "total_receipt_amount", "allocatable_amount", "exception_amount", "line_count", "allocatable_line_count", "exception_line_count", "duplicate_line_count", "blocker_count", "warning_count", "created_on"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
        "submitted_journal_entries_today": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
    }
    return {
        "mapping_rules": mapping_rules,
        "previews": previews,
        "guardrails": guardrails,
        "preview_only_confirmation": PREVIEW_ONLY_CONFIRMATION,
        "note": "Payment Entry design summary only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
    }


def execute_mapping_rule_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("m.status = %(status)s")
        params["status"] = filters.status
    if filters.get("payer_type"):
        conditions.append("m.payer_type = %(payer_type)s")
        params["payer_type"] = filters.payer_type
    if filters.get("company"):
        conditions.append("m.company = %(company)s")
        params["company"] = filters.company

    columns = [
        {"fieldname": "mapping_rule", "label": _("Mapping Rule"), "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "width": 220},
        {"fieldname": "mapping_id", "label": _("Mapping ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "mapping_name", "label": _("Mapping Name"), "fieldtype": "Data", "width": 300},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "payer_type", "label": _("Payer Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "mapping_scope", "label": _("Scope"), "fieldtype": "Data", "width": 160},
        {"fieldname": "bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "receivable_account", "label": _("Receivable Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "payment_entry_creation_allowed", "label": _("PE Creation"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_count", "label": _("Previews"), "fieldtype": "Int", "width": 90},
        {"fieldname": "last_preview_on", "label": _("Last Preview On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT m.name AS mapping_rule, m.mapping_id, m.mapping_name, m.status, m.company, m.payer_type,
            m.mapping_scope, m.bank_account, m.receivable_account, m.payment_entry_creation_allowed,
            m.preview_count, m.last_preview_on
        FROM `tabNDIS Payment Entry Mapping Rule` m
        {build_where(conditions)}
        ORDER BY m.mapping_id ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Draft"] = chart_map.get(row.status or "Draft", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Mapping Rules", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Mapping Rules"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Active"]), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": len([row for row in data if not row.bank_account]), "indicator": "Orange", "label": _("Missing Bank"), "datatype": "Int"},
        {"value": len([row for row in data if row.payment_entry_creation_allowed]), "indicator": "Red", "label": _("PE Creation Flags"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_allocation_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["status", "validation_status", "mapping_rule", "remittance_import"]:
        if filters.get(fieldname):
            conditions.append(f"p.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    if filters.get("from_date"):
        conditions.append("DATE(p.created_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(p.created_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "allocation_preview", "label": _("Allocation Preview"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 300},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "validation_status", "label": _("Validation"), "fieldtype": "Data", "width": 110},
        {"fieldname": "mapping_rule", "label": _("Mapping Rule"), "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "width": 220},
        {"fieldname": "remittance_import", "label": _("Remittance Import"), "fieldtype": "Link", "options": "NDIS Remittance Import", "width": 220},
        {"fieldname": "total_receipt_amount", "label": _("Receipt Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "allocatable_amount", "label": _("Allocatable"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "exception_amount", "label": _("Exception"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "allocatable_line_count", "label": _("Allocatable Lines"), "fieldtype": "Int", "width": 120},
        {"fieldname": "exception_line_count", "label": _("Exception Lines"), "fieldtype": "Int", "width": 120},
        {"fieldname": "duplicate_line_count", "label": _("Duplicates"), "fieldtype": "Int", "width": 100},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS allocation_preview, p.preview_id, p.status, p.validation_status, p.mapping_rule,
            p.remittance_import, p.total_receipt_amount, p.allocatable_amount, p.exception_amount,
            p.line_count, p.allocatable_line_count, p.exception_line_count, p.duplicate_line_count,
            p.blocker_count, p.warning_count, p.created_on, %(currency)s AS currency
        FROM `tabNDIS Payment Entry Allocation Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.preview_id for row in data[:20]], "datasets": [{"name": "Allocatable", "values": [flt(row.allocatable_amount) for row in data[:20]]}, {"name": "Exception", "values": [flt(row.exception_amount) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(flt(row.allocatable_amount) for row in data), "indicator": "Green", "label": _("Allocatable"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.exception_amount) for row in data), "indicator": "Orange", "label": _("Exception"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.duplicate_line_count or 0) for row in data), "indicator": "Red", "label": _("Duplicates"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_allocation_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("allocation_preview"):
        conditions.append("l.allocation_preview = %(allocation_preview)s")
        params["allocation_preview"] = filters.allocation_preview
    if filters.get("status"):
        conditions.append("l.status = %(status)s")
        params["status"] = filters.status
    if filters.get("allocation_decision"):
        conditions.append("l.allocation_decision = %(allocation_decision)s")
        params["allocation_decision"] = filters.allocation_decision
    if filters.get("sales_invoice"):
        conditions.append("l.sales_invoice = %(sales_invoice)s")
        params["sales_invoice"] = filters.sales_invoice

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview Line", "width": 220},
        {"fieldname": "allocation_preview", "label": _("Allocation Preview"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_label", "label": _("Line Label"), "fieldtype": "Data", "width": 240},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "receipt_amount", "label": _("Receipt"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "allocation_amount", "label": _("Allocation"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "exception_amount", "label": _("Exception"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "outcome_status", "label": _("Outcome"), "fieldtype": "Data", "width": 150},
        {"fieldname": "allocation_decision", "label": _("Decision"), "fieldtype": "Data", "width": 230},
        {"fieldname": "duplicate_detected", "label": _("Duplicate"), "fieldtype": "Check", "width": 90},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 360},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 360},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.allocation_preview, l.status, l.line_no, l.line_label, l.sales_invoice,
            l.receipt_amount, l.allocation_amount, l.exception_amount, l.outcome_status,
            l.allocation_decision, l.duplicate_detected, l.block_reason, l.recommendation,
            %(currency)s AS currency
        FROM `tabNDIS Payment Entry Allocation Preview Line` l
        {build_where(conditions)}
        ORDER BY
            CASE l.status
                WHEN 'Exception' THEN 1
                WHEN 'Duplicate' THEN 2
                WHEN 'Excluded' THEN 3
                WHEN 'Allocatable' THEN 4
                ELSE 5
            END,
            l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Exception"] = chart_map.get(row.status or "Exception", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Allocatable"]), "indicator": "Green", "label": _("Allocatable"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Exception"]), "indicator": "Orange", "label": _("Exceptions"), "datatype": "Int"},
        {"value": len([row for row in data if row.duplicate_detected]), "indicator": "Red", "label": _("Duplicates"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
