import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SANDBOX_ACK = "I_CONFIRM_NDIS_FINANCE_SANDBOX_JE_DRAFT_ONLY"
DRAFT_ONLY_CONFIRMATION = "SANDBOX_DRAFT_JOURNAL_ENTRY_ONLY_NO_SUBMIT_NO_GL"
VALID_JE_REFERENCE_TYPES = {
    "Sales Invoice",
    "Purchase Invoice",
    "Journal Entry",
    "Sales Order",
    "Purchase Order",
    "Expense Claim",
    "Asset",
    "Loan",
    "Payroll Entry",
    "Employee Advance",
    "Exchange Rate Revaluation",
    "Invoice Discounting",
}


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-JE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def is_local_sandbox_site():
    site = frappe.local.site or ""
    if "localhost" in site or site.startswith("dev.") or site.startswith("test."):
        return True
    return int(frappe.conf.get("ndis_finance_allow_non_local_sandbox_posting") or 0) == 1


def validate_sandbox_config():
    errors = []
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    if not sandbox_enabled:
        errors.append("Site config ndis_finance_sandbox_posting_enabled is not enabled.")
    if production_mode:
        errors.append("Site config ndis_finance_production_mode is enabled.")
    if not is_local_sandbox_site():
        errors.append("Site name is not recognised as localhost/dev/test and non-local sandbox override is not enabled.")
    return {
        "sandbox_enabled": sandbox_enabled,
        "production_mode": production_mode,
        "is_local_sandbox_site": is_local_sandbox_site(),
        "errors": errors,
    }


def get_request(posting_request):
    if not frappe.db.exists("NDIS Accounting Posting Request", posting_request):
        frappe.throw(_("NDIS Accounting Posting Request not found: {0}").format(posting_request))
    return frappe.get_doc("NDIS Accounting Posting Request", posting_request)


def get_request_lines(posting_request):
    return frappe.get_all(
        "NDIS Accounting Posting Request Line",
        filters={"posting_request": posting_request, "status": ["!=", "Cancelled"]},
        fields=[
            "name",
            "status",
            "line_no",
            "line_label",
            "line_type",
            "target_entry_type",
            "account",
            "cost_center",
            "party_type",
            "party",
            "amount",
            "reference_doctype",
            "reference_name",
            "note",
        ],
        order_by="line_no asc, creation asc",
    )


def validate_account(account, company=None):
    if not account:
        return ["Account is missing."]
    if not frappe.db.exists("Account", account):
        return [f"Account does not exist: {account}"]
    account_doc = frappe.get_doc("Account", account)
    errors = []
    if int(account_doc.is_group or 0):
        errors.append(f"Account is group account: {account}")
    if company and account_doc.company != company:
        errors.append(f"Account {account} does not belong to company {company}.")
    if account_doc.account_type in ["Receivable", "Payable"]:
        errors.append(f"Account {account} is {account_doc.account_type}; sandbox fallback lines must not require party allocation.")
    return errors


def get_default_cost_center(company):
    if not company:
        return None
    rows = frappe.get_all(
        "Cost Center",
        filters={"company": company, "is_group": 0, "disabled": 0},
        fields=["name"],
        order_by="creation asc",
        limit=1,
    )
    return rows[0].name if rows else None


def prepare_lines_from_request(request_doc, debit_account=None, credit_account=None, amount=None, cost_center=None):
    request_lines = get_request_lines(request_doc.name)
    prepared = []
    debit_lines = [row for row in request_lines if row.line_type == "Debit" and flt(row.amount) > 0 and row.account]
    credit_lines = [row for row in request_lines if row.line_type == "Credit" and flt(row.amount) > 0 and row.account]
    if debit_lines and credit_lines:
        for row in debit_lines:
            prepared.append(line_from_request(row, "Debit", row.account, row.cost_center or cost_center, flt(row.amount), 0))
        for row in credit_lines:
            prepared.append(line_from_request(row, "Credit", row.account, row.cost_center or cost_center, 0, flt(row.amount)))
        return prepared

    amount = flt(amount or request_doc.request_total_amount or 0)
    if amount <= 0:
        frappe.throw(_("No debit/credit request lines were found and no positive fallback amount was supplied."))
    if not debit_account or not credit_account:
        frappe.throw(_("No debit/credit request lines were found. Provide debit_account, credit_account and amount for sandbox-only fallback test lines."))
    prepared.append(
        {
            "posting_request_line": None,
            "line_no": 1,
            "line_label": "Sandbox Fallback Debit",
            "line_type": "Debit",
            "account": debit_account,
            "cost_center": cost_center,
            "party_type": None,
            "party": None,
            "debit_amount": amount,
            "credit_amount": 0,
            "reference_doctype": request_doc.source_doctype,
            "reference_name": request_doc.source_name,
            "note": "Sandbox fallback debit line. Used because request had no debit/credit accounting lines.",
        }
    )
    prepared.append(
        {
            "posting_request_line": None,
            "line_no": 2,
            "line_label": "Sandbox Fallback Credit",
            "line_type": "Credit",
            "account": credit_account,
            "cost_center": cost_center,
            "party_type": None,
            "party": None,
            "debit_amount": 0,
            "credit_amount": amount,
            "reference_doctype": request_doc.source_doctype,
            "reference_name": request_doc.source_name,
            "note": "Sandbox fallback credit line. Used because request had no debit/credit accounting lines.",
        }
    )
    return prepared


def line_from_request(row, line_type, account, cost_center, debit_amount, credit_amount):
    return {
        "posting_request_line": row.name,
        "line_no": row.line_no,
        "line_label": row.line_label or line_type,
        "line_type": line_type,
        "account": account,
        "cost_center": cost_center,
        "party_type": row.party_type,
        "party": row.party,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "reference_doctype": row.reference_doctype,
        "reference_name": row.reference_name,
        "note": row.note,
    }


def validate_request_for_sandbox(request_doc):
    errors = []
    warnings = []
    if request_doc.status != "Dry Run Passed":
        errors.append("Posting request must be in status Dry Run Passed.")
    if request_doc.approval_status != "Approved":
        errors.append("Posting request must be CFO-approved.")
    if int(request_doc.blocker_count or 0):
        errors.append("Posting request has blockers.")
    if not int(request_doc.readiness_allowed or 0):
        errors.append("Production readiness is not allowed on the request.")
    if not int(request_doc.governance_signed_off or 0):
        errors.append("Governance pack is not signed off on the request.")
    if not int(request_doc.hard_posting_block or 0):
        errors.append("Hard posting block is not enabled on the request.")
    if int(request_doc.real_posting_enabled or 0):
        errors.append("real_posting_enabled is unexpectedly enabled on the request.")
    if request_doc.target_entry_type not in ["Journal Entry", "None", "", None]:
        warnings.append(f"Request target entry type is {request_doc.target_entry_type}. Phase 2D only creates sandbox Draft Journal Entry.")
    return errors, warnings


def validate_lines(lines, company):
    errors = []
    debit_total = sum(flt(row["debit_amount"]) for row in lines)
    credit_total = sum(flt(row["credit_amount"]) for row in lines)
    if debit_total <= 0 or credit_total <= 0:
        errors.append("Debit and credit totals must both be positive.")
    if round(debit_total - credit_total, 2) != 0:
        errors.append(f"Debit/Credit totals do not balance. Debit={debit_total}, Credit={credit_total}.")
    for row in lines:
        errors.extend(validate_account(row.get("account"), company=company))
    return errors, debit_total, credit_total, debit_total - credit_total


def create_draft_journal_entry(request_doc, run_name, lines, acknowledgement):
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = request_doc.company
    je.posting_date = request_doc.posting_date or today()
    je.user_remark = (
        "NDIS SANDBOX DRAFT ONLY - DO NOT SUBMIT. "
        f"Posting Request: {request_doc.name}. Sandbox Run: {run_name}. "
        "No GL Entry should be created from this draft."
    )
    for row in lines:
        account_row = {
            "account": row["account"],
            "debit_in_account_currency": flt(row["debit_amount"]),
            "credit_in_account_currency": flt(row["credit_amount"]),
            "user_remark": row.get("note"),
        }
        if row.get("reference_doctype") in VALID_JE_REFERENCE_TYPES and row.get("reference_name"):
            account_row["reference_type"] = row.get("reference_doctype")
            account_row["reference_name"] = row.get("reference_name")
        if row.get("cost_center"):
            account_row["cost_center"] = row.get("cost_center")
        if row.get("party_type") and row.get("party"):
            account_row["party_type"] = row.get("party_type")
            account_row["party"] = row.get("party")
        je.append("accounts", account_row)

    if je.meta.has_field("custom_ndis_sandbox_posting_run"):
        je.custom_ndis_sandbox_posting_run = run_name
    if je.meta.has_field("custom_ndis_accounting_posting_request"):
        je.custom_ndis_accounting_posting_request = request_doc.name
    if je.meta.has_field("custom_ndis_sandbox_draft_only"):
        je.custom_ndis_sandbox_draft_only = 1
    if je.meta.has_field("custom_ndis_sandbox_acknowledgement"):
        je.custom_ndis_sandbox_acknowledgement = acknowledgement
    je.insert(ignore_permissions=True)
    return je.name


@frappe.whitelist()
def create_sandbox_journal_entry_draft(posting_request, acknowledgement=None, debit_account=None, credit_account=None, amount=None, cost_center=None, dry_run=0, notes=None):
    assert_action("create_sandbox_journal_entry_draft")
    request_doc = get_request(posting_request)
    sandbox_config = validate_sandbox_config()
    validation_errors = []
    validation_warnings = []
    if acknowledgement != SANDBOX_ACK:
        validation_errors.append(f"Invalid acknowledgement. Required: {SANDBOX_ACK}")
    validation_errors.extend(sandbox_config["errors"])
    request_errors, request_warnings = validate_request_for_sandbox(request_doc)
    validation_errors.extend(request_errors)
    validation_warnings.extend(request_warnings)

    company = request_doc.company or frappe.defaults.get_user_default("Company")
    if not company:
        validation_errors.append("Company could not be determined from posting request or user defaults.")
    cost_center = cost_center or get_default_cost_center(company)
    request_doc.company = company
    lines = []
    debit_total = 0
    credit_total = 0
    variance = 0
    if not validation_errors:
        lines = prepare_lines_from_request(request_doc, debit_account=debit_account, credit_account=credit_account, amount=amount, cost_center=cost_center)
        line_errors, debit_total, credit_total, variance = validate_lines(lines, company)
        validation_errors.extend(line_errors)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "posting_request": posting_request,
        "sandbox_config": sandbox_config,
        "required_acknowledgement": SANDBOX_ACK,
        "acknowledgement_ok": acknowledgement == SANDBOX_ACK,
        "company": company,
        "cost_center": cost_center,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "variance_amount": variance,
        "line_count": len(lines),
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "prepared_lines": lines,
        "draft_only_confirmation": DRAFT_ONLY_CONFIRMATION,
        "note": "Sandbox validation only. No accounting document created." if int(dry_run or 0) else "Sandbox Draft Journal Entry creation requested.",
    }
    if int(dry_run or 0):
        return result

    if validation_errors:
        run = create_run_record(request_doc, "Blocked", acknowledgement, company, cost_center, debit_total, credit_total, variance, lines, result, notes=notes)
        frappe.db.commit()
        result.update({"created": False, "sandbox_run": run.name, "status": "Blocked"})
        return result

    run = create_run_record(request_doc, "Draft", acknowledgement, company, cost_center, debit_total, credit_total, variance, lines, result, notes=notes)
    journal_entry = create_draft_journal_entry(request_doc, run.name, lines, acknowledgement)
    frappe.db.set_value(
        "NDIS Sandbox Accounting Posting Run",
        run.name,
        {"status": "Created Draft JE", "journal_entry": journal_entry, "journal_entry_docstatus": 0},
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Sandbox Accounting Posting Run Line`
        SET status = 'Inserted In Draft JE'
        WHERE sandbox_run = %(sandbox_run)s
        """,
        {"sandbox_run": run.name},
    )
    frappe.db.commit()
    result.update(
        {
            "created": True,
            "sandbox_run": run.name,
            "run_id": run.run_id,
            "journal_entry": journal_entry,
            "journal_entry_docstatus": 0,
            "status": "Created Draft JE",
            "note": "Sandbox Draft Journal Entry created only. It was not submitted. No GL Entry, Payment Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, bank allocation, or payment movement created.",
        }
    )
    return result


def create_run_record(request_doc, status, acknowledgement, company, cost_center, debit_total, credit_total, variance, lines, validation_log, notes=None):
    run = frappe.new_doc("NDIS Sandbox Accounting Posting Run")
    run.run_id = make_run_id()
    run.status = status
    run.sandbox_mode = 1
    run.draft_only = 1
    run.posting_request = request_doc.name
    run.posting_preview = request_doc.posting_preview
    run.policy = request_doc.policy
    run.event_type = request_doc.event_type
    run.source_doctype = request_doc.source_doctype
    run.source_name = request_doc.source_name
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    run.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    run.readiness_check = request_doc.readiness_check
    run.readiness_allowed = int(request_doc.readiness_allowed or 0)
    run.governance_pack = request_doc.governance_pack
    run.governance_signed_off = int(request_doc.governance_signed_off or 0)
    run.request_approved = 1 if request_doc.approval_status == "Approved" else 0
    run.request_dry_run_passed = 1 if request_doc.status == "Dry Run Passed" else 0
    run.hard_posting_block_confirmed = int(request_doc.hard_posting_block or 0)
    run.real_posting_disabled_confirmed = 0 if int(request_doc.real_posting_enabled or 0) else 1
    run.acknowledgement = acknowledgement
    run.required_acknowledgement = SANDBOX_ACK
    run.company = company
    run.posting_date = request_doc.posting_date or today()
    run.currency = request_doc.currency or currency()
    run.total_debit = debit_total
    run.total_credit = credit_total
    run.variance_amount = variance
    run.line_count = len(lines)
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation_log)
    run.notes = notes
    run.insert(ignore_permissions=True)
    for row in lines:
        line = frappe.new_doc("NDIS Sandbox Accounting Posting Run Line")
        line.sandbox_run = run.name
        line.posting_request_line = row.get("posting_request_line")
        line.status = "Prepared" if status != "Blocked" else "Blocker"
        line.line_no = row.get("line_no")
        line.line_label = row.get("line_label")
        line.line_type = row.get("line_type")
        line.account = row.get("account")
        line.cost_center = row.get("cost_center") or cost_center
        line.party_type = row.get("party_type")
        line.party = row.get("party")
        line.debit_amount = flt(row.get("debit_amount"))
        line.credit_amount = flt(row.get("credit_amount"))
        line.reference_doctype = row.get("reference_doctype")
        line.reference_name = row.get("reference_name")
        line.note = row.get("note")
        line.insert(ignore_permissions=True)
    return run


@frappe.whitelist()
def cancel_sandbox_accounting_posting_run(sandbox_run, reason=None):
    assert_action("cancel_sandbox_accounting_posting_run")
    if not frappe.db.exists("NDIS Sandbox Accounting Posting Run", sandbox_run):
        frappe.throw(_("Sandbox Accounting Posting Run not found: {0}").format(sandbox_run))
    run = frappe.get_doc("NDIS Sandbox Accounting Posting Run", sandbox_run)
    if run.journal_entry:
        docstatus = frappe.db.get_value("Journal Entry", run.journal_entry, "docstatus")
        if int(docstatus or 0) == 1:
            frappe.throw(_("Linked Journal Entry is submitted. This should not happen for Phase 2D sandbox draft-only runs."))
        je = frappe.get_doc("Journal Entry", run.journal_entry)
        je.user_remark = (je.user_remark or "") + f"\nSandbox run cancelled: {reason or 'No reason supplied'}"
        je.save(ignore_permissions=True)
    frappe.db.set_value(
        "NDIS Sandbox Accounting Posting Run",
        sandbox_run,
        {"status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "validation_log": reason or "Sandbox run cancelled."},
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Sandbox Accounting Posting Run Line`
        SET status = 'Cancelled'
        WHERE sandbox_run = %(sandbox_run)s
        """,
        {"sandbox_run": sandbox_run},
    )
    frappe.db.commit()
    return {
        "sandbox_run": sandbox_run,
        "status": "Cancelled",
        "journal_entry": run.journal_entry,
        "note": "Sandbox run cancelled internally. Draft Journal Entry was not submitted and no GL/payment movement was created.",
    }


def block_sandbox_journal_entry_submit(doc, method=None):
    if int(doc.get("custom_ndis_sandbox_draft_only") or 0):
        frappe.throw(_("This is an NDIS sandbox draft-only Journal Entry and cannot be submitted. No GL Entry may be created from Phase 2D sandbox records."))
    if "NDIS SANDBOX DRAFT ONLY" in (doc.get("user_remark") or ""):
        frappe.throw(_("This Journal Entry is marked as NDIS SANDBOX DRAFT ONLY and cannot be submitted."))


@frappe.whitelist()
def quick_sandbox_accounting_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Sandbox Accounting Posting Run",
        fields=["name", "run_id", "status", "posting_request", "journal_entry", "journal_entry_docstatus", "sandbox_mode", "draft_only", "company", "total_debit", "total_credit", "variance_amount", "line_count", "created_on", "created_by_user"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Sandbox Accounting Posting Run Line",
        fields=["name", "sandbox_run", "status", "line_no", "line_label", "line_type", "account", "debit_amount", "credit_amount", "reference_doctype", "reference_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "submitted_sandbox_journal_entries": frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 1}),
        "draft_sandbox_journal_entries": frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 0}),
        "gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
    }
    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement": SANDBOX_ACK,
        "draft_only_confirmation": DRAFT_ONLY_CONFIRMATION,
        "note": "Sandbox summary only. Draft Journal Entries may exist, but no submitted Journal Entry, GL Entry, Payment Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, bank allocation, or payment movement should be created.",
    }


def execute_sandbox_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["status", "posting_request", "journal_entry"]:
        if filters.get(fieldname):
            conditions.append(f"r.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    if filters.get("from_date"):
        conditions.append("DATE(r.created_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(r.created_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run", "width": 220},
        {"fieldname": "run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 290},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "posting_request", "label": _("Posting Request"), "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "width": 220},
        {"fieldname": "journal_entry", "label": _("Draft Journal Entry"), "fieldtype": "Link", "options": "Journal Entry", "width": 180},
        {"fieldname": "journal_entry_docstatus", "label": _("JE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "total_debit", "label": _("Total Debit"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "total_credit", "label": _("Total Credit"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "variance_amount", "label": _("Variance"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "sandbox_config_enabled", "label": _("Sandbox Config"), "fieldtype": "Check", "width": 120},
        {"fieldname": "production_mode_detected", "label": _("Production Mode"), "fieldtype": "Check", "width": 120},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS sandbox_run, r.run_id, r.status, r.posting_request, r.journal_entry,
            r.journal_entry_docstatus, r.company, r.total_debit, r.total_credit, r.variance_amount,
            r.line_count, r.sandbox_config_enabled, r.production_mode_detected, r.created_on,
            %(currency)s AS currency
        FROM `tabNDIS Sandbox Accounting Posting Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.run_id for row in data[:20]], "datasets": [{"name": "Debit", "values": [flt(row.total_debit) for row in data[:20]]}, {"name": "Credit", "values": [flt(row.total_credit) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runs"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Created Draft JE"]), "indicator": "Green", "label": _("Draft JEs Created"), "datatype": "Int"},
        {"value": len([row for row in data if row.journal_entry_docstatus == 1]), "indicator": "Red", "label": _("Submitted JEs"), "datatype": "Int"},
        {"value": sum(flt(row.total_debit) for row in data), "indicator": "Blue", "label": _("Total Debit"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_sandbox_run_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["sandbox_run", "status", "line_type", "account"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run Line", "width": 220},
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_label", "label": _("Line Label"), "fieldtype": "Data", "width": 260},
        {"fieldname": "line_type", "label": _("Line Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Link", "options": "Cost Center", "width": 180},
        {"fieldname": "debit_amount", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "credit_amount", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "reference_doctype", "label": _("Reference DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "reference_name", "label": _("Reference Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.sandbox_run, l.status, l.line_no, l.line_label, l.line_type,
            l.account, l.cost_center, l.debit_amount, l.credit_amount, l.reference_doctype,
            l.reference_name, l.note, %(currency)s AS currency
        FROM `tabNDIS Sandbox Accounting Posting Run Line` l
        {build_where(conditions)}
        ORDER BY l.creation DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": ["Debit", "Credit"], "datasets": [{"name": "Amount", "values": [sum(flt(row.debit_amount) for row in data), sum(flt(row.credit_amount) for row in data)]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(flt(row.debit_amount) for row in data), "indicator": "Blue", "label": _("Debit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.credit_amount) for row in data), "indicator": "Green", "label": _("Credit"), "datatype": "Currency", "currency": currency()},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
