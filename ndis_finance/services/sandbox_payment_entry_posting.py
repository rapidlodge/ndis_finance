import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SANDBOX_PE_ACK = "I_CONFIRM_NDIS_FINANCE_SANDBOX_PAYMENT_ENTRY_DRAFT_ONLY"
DRAFT_ONLY_CONFIRMATION = "SANDBOX_DRAFT_PAYMENT_ENTRY_ONLY_NO_SUBMIT_NO_GL"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-PE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def validate_sandbox_config():
    errors = []
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    site = frappe.local.site or ""
    local_ok = "localhost" in site or site.startswith("dev.") or site.startswith("test.")
    if not sandbox_enabled:
        errors.append("Site config ndis_finance_sandbox_posting_enabled is not enabled.")
    if production_mode:
        errors.append("Site config ndis_finance_production_mode is enabled.")
    if not local_ok and not int(frappe.conf.get("ndis_finance_allow_non_local_sandbox_posting") or 0):
        errors.append("Site name is not recognised as localhost/dev/test and non-local sandbox override is not enabled.")
    return {"sandbox_enabled": sandbox_enabled, "production_mode": production_mode, "local_site_ok": local_ok, "errors": errors}


def get_preview(allocation_preview):
    if not frappe.db.exists("NDIS Payment Entry Allocation Preview", allocation_preview):
        frappe.throw(_("NDIS Payment Entry Allocation Preview not found: {0}").format(allocation_preview))
    return frappe.get_doc("NDIS Payment Entry Allocation Preview", allocation_preview)


def get_mapping(mapping_rule):
    if not frappe.db.exists("NDIS Payment Entry Mapping Rule", mapping_rule):
        frappe.throw(_("NDIS Payment Entry Mapping Rule not found: {0}").format(mapping_rule))
    return frappe.get_doc("NDIS Payment Entry Mapping Rule", mapping_rule)


def validate_account(account, company=None):
    errors = []
    if not account:
        return ["Account is missing."]
    if not frappe.db.exists("Account", account):
        return [f"Account does not exist: {account}"]
    account_doc = frappe.get_doc("Account", account)
    if int(account_doc.is_group or 0):
        errors.append(f"Account is a group account: {account}")
    if company and account_doc.company != company:
        errors.append(f"Account {account} does not belong to company {company}.")
    return errors


def get_allocatable_lines(allocation_preview):
    return frappe.get_all(
        "NDIS Payment Entry Allocation Preview Line",
        filters={"allocation_preview": allocation_preview, "status": "Allocatable"},
        fields=[
            "name",
            "line_no",
            "line_label",
            "sales_invoice",
            "invoice_status",
            "receipt_amount",
            "allocation_amount",
            "invoice_outstanding_amount",
            "outcome_status",
            "allocation_decision",
            "duplicate_key",
            "duplicate_detected",
            "block_reason",
        ],
        order_by="line_no asc, creation asc",
        limit=10000,
    )


def get_non_allocatable_counts(allocation_preview):
    rows = frappe.get_all(
        "NDIS Payment Entry Allocation Preview Line",
        filters={"allocation_preview": allocation_preview, "status": ["!=", "Cancelled"]},
        fields=["status", "duplicate_detected"],
        limit=10000,
    )
    return {
        "source_line_count": len(rows),
        "excluded_line_count": len([row for row in rows if row.status in ["Exception", "Excluded"]]),
        "duplicate_line_count": len([row for row in rows if row.status == "Duplicate" or int(row.duplicate_detected or 0)]),
        "blocked_line_count": len([row for row in rows if row.status in ["Exception", "Duplicate", "Excluded"]]),
    }


def invoice_customer(sales_invoice):
    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        return None
    return frappe.db.get_value("Sales Invoice", sales_invoice, "customer")


def invoice_outstanding(sales_invoice):
    if not sales_invoice or not frappe.db.exists("Sales Invoice", sales_invoice):
        return 0
    return flt(frappe.db.get_value("Sales Invoice", sales_invoice, "outstanding_amount") or 0)


def prepare_lines(lines, fallback_customer=None):
    prepared = []
    customers = set()
    for row in lines:
        customer = invoice_customer(row.sales_invoice) or fallback_customer
        outstanding = invoice_outstanding(row.sales_invoice)
        if customer:
            customers.add(customer)
        prepared.append(
            frappe._dict(
                {
                    "allocation_preview_line": row.name,
                    "line_no": row.line_no,
                    "line_label": row.line_label,
                    "status": "Included In Draft PE",
                    "sales_invoice": row.sales_invoice,
                    "customer": customer,
                    "invoice_status": row.invoice_status,
                    "receipt_amount": flt(row.receipt_amount),
                    "allocation_amount": flt(row.allocation_amount),
                    "outstanding_amount": outstanding,
                    "source_status": row.outcome_status,
                    "decision": row.allocation_decision,
                    "duplicate_key": row.duplicate_key,
                    "block_reason": row.block_reason,
                    "payment_entry_reference_created": 0,
                    "preview_only_note": "Draft Payment Entry reference only. Not submitted.",
                }
            )
        )
    return prepared, customers


def validate_preview_and_mapping(preview_doc, mapping_doc, acknowledgement, fallback_customer=None, bank_account=None, receivable_account=None):
    errors = []
    warnings = []
    if acknowledgement != SANDBOX_PE_ACK:
        errors.append(f"Invalid acknowledgement. Required: {SANDBOX_PE_ACK}")
    if preview_doc.status not in ["Previewed", "Needs Review"]:
        errors.append(f"Allocation preview status must be Previewed or Needs Review. Current: {preview_doc.status}")
    if preview_doc.validation_status == "Blocked" or int(preview_doc.blocker_count or 0):
        errors.append("Allocation preview is blocked.")
    if not int(preview_doc.design_approved or 0):
        errors.append("Allocation preview does not have approved Phase 3A design evidence.")
    if not int(preview_doc.sandbox_completion_allowed or 0):
        errors.append("Allocation preview does not have sandbox completion gate allowed.")
    if int(preview_doc.payment_entry_creation_allowed or 0):
        errors.append("Allocation preview unexpectedly has payment_entry_creation_allowed enabled.")
    if preview_doc.preview_only_confirmation != "PAYMENT_ENTRY_ALLOCATION_PREVIEW_ONLY_NO_PAYMENT_ENTRY":
        warnings.append("Preview-only confirmation value is not recognised from Phase 3B.")
    if mapping_doc.status != "Active":
        warnings.append(f"Mapping rule is {mapping_doc.status}. Draft mapping is allowed for sandbox test only.")
    if int(mapping_doc.payment_entry_creation_allowed or 0):
        errors.append("Mapping rule has payment_entry_creation_allowed enabled. Phase 3C must remain sandbox draft only.")

    company = preview_doc.company or mapping_doc.company or frappe.defaults.get_user_default("Company")
    paid_to = bank_account or preview_doc.bank_account or mapping_doc.bank_account
    paid_from = receivable_account or preview_doc.receivable_account or mapping_doc.receivable_account
    if not company:
        errors.append("Company could not be determined.")
    if not paid_to:
        errors.append("Bank account / paid_to account is missing. Provide bank_account fallback or configure mapping rule.")
    if not paid_from:
        errors.append("Receivable account / paid_from account is missing. Provide receivable_account fallback or configure mapping rule.")
    if company:
        errors.extend(validate_account(paid_to, company))
        errors.extend(validate_account(paid_from, company))
    if fallback_customer and not frappe.db.exists("Customer", fallback_customer):
        errors.append(f"Fallback customer does not exist: {fallback_customer}")
    return errors, warnings, company, paid_from, paid_to


def create_run_record(preview_doc, mapping_doc, status, acknowledgement, company, paid_from, paid_to, party, prepared_lines, validation_result, notes=None):
    total = sum(flt(row.allocation_amount) for row in prepared_lines)
    counts = get_non_allocatable_counts(preview_doc.name)
    run = frappe.new_doc("NDIS Sandbox Payment Entry Run")
    run.run_id = make_run_id()
    run.status = status
    run.sandbox_mode = 1
    run.draft_only = 1
    run.allocation_preview = preview_doc.name
    run.mapping_rule = mapping_doc.name
    run.remittance_import = preview_doc.remittance_import
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    run.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    run.sandbox_completion_gate = preview_doc.sandbox_completion_gate
    run.sandbox_completion_allowed = int(preview_doc.sandbox_completion_allowed or 0)
    run.design_review = preview_doc.design_review
    run.design_approved = int(preview_doc.design_approved or 0)
    run.preview_validation_status = preview_doc.validation_status
    run.required_acknowledgement = SANDBOX_PE_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = 1 if acknowledgement == SANDBOX_PE_ACK else 0
    run.payment_entry_docstatus = 0
    run.payment_type = "Receive"
    run.party_type = "Customer"
    run.party = party
    run.company = company
    run.posting_date = today()
    run.mode_of_payment = preview_doc.mode_of_payment or mapping_doc.mode_of_payment
    run.paid_from = paid_from
    run.paid_to = paid_to
    run.currency = preview_doc.currency or currency()
    run.paid_amount = total
    run.received_amount = total
    run.source_line_count = counts["source_line_count"]
    run.included_line_count = len(prepared_lines)
    run.excluded_line_count = counts["excluded_line_count"]
    run.duplicate_line_count = counts["duplicate_line_count"]
    run.blocked_line_count = counts["blocked_line_count"]
    run.total_allocation_amount = total
    run.blocker_count = len(validation_result.get("errors", []))
    run.warning_count = len(validation_result.get("warnings", []))
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation_result)
    run.notes = notes
    run.insert(ignore_permissions=True)

    for row in prepared_lines:
        line = frappe.new_doc("NDIS Sandbox Payment Entry Run Line")
        line.sandbox_run = run.name
        line.allocation_preview_line = row.allocation_preview_line
        line.status = row.status if status != "Blocked" else "Blocked"
        line.line_no = row.line_no
        line.line_label = row.line_label
        line.sales_invoice = row.sales_invoice
        line.customer = row.customer
        line.invoice_status = row.invoice_status
        line.receipt_amount = row.receipt_amount
        line.allocation_amount = row.allocation_amount
        line.outstanding_amount = row.outstanding_amount
        line.source_status = row.source_status
        line.decision = row.decision
        line.duplicate_key = row.duplicate_key
        line.block_reason = row.block_reason
        line.payment_entry_reference_created = 0
        line.preview_only_note = row.preview_only_note
        line.insert(ignore_permissions=True)
    return run


def set_if_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def create_draft_payment_entry(preview_doc, mapping_doc, run_name, company, paid_from, paid_to, party, prepared_lines, acknowledgement):
    total = sum(flt(row.allocation_amount) for row in prepared_lines)
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = company
    pe.posting_date = today()
    pe.mode_of_payment = preview_doc.mode_of_payment or mapping_doc.mode_of_payment
    pe.party_type = "Customer"
    pe.party = party
    pe.paid_from = paid_from
    pe.paid_to = paid_to
    pe.paid_amount = total
    pe.received_amount = total
    pe.reference_no = run_name
    pe.reference_date = today()
    pe.remarks = (
        "NDIS SANDBOX DRAFT PAYMENT ENTRY ONLY - DO NOT SUBMIT. "
        f"Allocation Preview: {preview_doc.name}. Sandbox Run: {run_name}. "
        "No GL Entry or payment movement should be created from this draft."
    )
    set_if_field(pe, "custom_ndis_sandbox_payment_entry_run", run_name)
    set_if_field(pe, "custom_ndis_payment_entry_allocation_preview", preview_doc.name)
    set_if_field(pe, "custom_ndis_sandbox_payment_entry_draft_only", 1)
    set_if_field(pe, "custom_ndis_sandbox_payment_entry_acknowledgement", acknowledgement)
    for row in prepared_lines:
        pe.append("references", {"reference_doctype": "Sales Invoice", "reference_name": row.sales_invoice, "allocated_amount": flt(row.allocation_amount)})
    pe.insert(ignore_permissions=True, ignore_mandatory=True)
    return pe.name


@frappe.whitelist()
def create_sandbox_payment_entry_draft(allocation_preview, acknowledgement=None, bank_account=None, receivable_account=None, fallback_customer=None, dry_run=0, notes=None):
    assert_action("create_sandbox_payment_entry_draft")
    preview_doc = get_preview(allocation_preview)
    mapping_doc = get_mapping(preview_doc.mapping_rule)
    sandbox_config = validate_sandbox_config()
    errors = list(sandbox_config["errors"])
    validation_errors, warnings, company, paid_from, paid_to = validate_preview_and_mapping(
        preview_doc, mapping_doc, acknowledgement, fallback_customer=fallback_customer, bank_account=bank_account, receivable_account=receivable_account
    )
    errors.extend(validation_errors)
    allocatable_source_lines = get_allocatable_lines(allocation_preview)
    prepared_lines, customers = prepare_lines(allocatable_source_lines, fallback_customer=fallback_customer)
    if not prepared_lines:
        errors.append("No allocatable preview lines found. Rejected, short-paid, duplicate or unmatched lines cannot be used.")
    if len(customers) > 1:
        errors.append("Allocatable lines belong to multiple customers. One Payment Entry can only have one customer party.")
    party = list(customers)[0] if len(customers) == 1 else fallback_customer
    if not party:
        errors.append("Customer party could not be determined from Sales Invoice or fallback_customer.")
    for row in prepared_lines:
        if not row.sales_invoice or not frappe.db.exists("Sales Invoice", row.sales_invoice):
            errors.append(f"Sales Invoice missing for line {row.line_label}.")
        if flt(row.allocation_amount) <= 0:
            errors.append(f"Allocation amount must be positive for line {row.line_label}.")
        if flt(row.allocation_amount) > flt(row.outstanding_amount):
            errors.append(f"Allocation amount exceeds outstanding amount for invoice {row.sales_invoice}.")
    total = sum(flt(row.allocation_amount) for row in prepared_lines)
    if total <= 0:
        errors.append("Total allocation amount must be positive.")
    validation_result = {
        "dry_run": bool(int(dry_run or 0)),
        "allocation_preview": allocation_preview,
        "mapping_rule": mapping_doc.name,
        "sandbox_config": sandbox_config,
        "errors": errors,
        "warnings": warnings,
        "company": company,
        "party": party,
        "paid_from": paid_from,
        "paid_to": paid_to,
        "line_count": len(prepared_lines),
        "total_allocation_amount": total,
        "required_acknowledgement": SANDBOX_PE_ACK,
        "draft_only_confirmation": DRAFT_ONLY_CONFIRMATION,
        "prepared_lines": prepared_lines,
        "note": "Sandbox validation only. No Payment Entry created." if int(dry_run or 0) else "Sandbox Draft Payment Entry creation requested.",
    }
    if int(dry_run or 0):
        return validation_result
    if errors:
        run = create_run_record(preview_doc, mapping_doc, "Blocked", acknowledgement, company, paid_from, paid_to, party, prepared_lines, validation_result, notes=notes)
        frappe.db.commit()
        validation_result.update({"created": False, "sandbox_run": run.name, "status": "Blocked"})
        return validation_result

    run = create_run_record(preview_doc, mapping_doc, "Validated", acknowledgement, company, paid_from, paid_to, party, prepared_lines, validation_result, notes=notes)
    try:
        payment_entry = create_draft_payment_entry(preview_doc, mapping_doc, run.name, company, paid_from, paid_to, party, prepared_lines, acknowledgement)
        frappe.db.set_value("NDIS Sandbox Payment Entry Run", run.name, {"status": "Created Draft Payment Entry", "payment_entry": payment_entry, "payment_entry_docstatus": 0}, update_modified=False)
        frappe.db.sql(
            "UPDATE `tabNDIS Sandbox Payment Entry Run Line` SET payment_entry_reference_created = 1 WHERE sandbox_run = %(sandbox_run)s",
            {"sandbox_run": run.name},
        )
        frappe.db.commit()
        validation_result.update(
            {
                "created": True,
                "sandbox_run": run.name,
                "run_id": run.run_id,
                "payment_entry": payment_entry,
                "payment_entry_docstatus": 0,
                "status": "Created Draft Payment Entry",
                "note": "Sandbox Draft Payment Entry created only. It was not submitted. No GL Entry, Journal Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
            }
        )
        return validation_result
    except Exception as exc:
        frappe.db.set_value("NDIS Sandbox Payment Entry Run", run.name, {"status": "Failed", "validation_log": safe_json({**validation_result, "payment_entry_insert_error": str(exc)})}, update_modified=False)
        frappe.db.commit()
        raise


@frappe.whitelist()
def cancel_sandbox_payment_entry_run(sandbox_run, reason=None):
    assert_action("cancel_sandbox_payment_entry_run")
    if not frappe.db.exists("NDIS Sandbox Payment Entry Run", sandbox_run):
        frappe.throw(_("Sandbox Payment Entry Run not found: {0}").format(sandbox_run))
    run = frappe.get_doc("NDIS Sandbox Payment Entry Run", sandbox_run)
    if run.payment_entry and frappe.db.exists("Payment Entry", run.payment_entry):
        docstatus = int(frappe.db.get_value("Payment Entry", run.payment_entry, "docstatus") or 0)
        if docstatus == 1:
            frappe.throw(_("Linked Payment Entry is submitted. Phase 3C sandbox Payment Entries must never be submitted."))
        pe = frappe.get_doc("Payment Entry", run.payment_entry)
        pe.remarks = (pe.remarks or "") + f"\nSandbox Payment Entry run cancelled: {reason or 'No reason supplied'}"
        pe.save(ignore_permissions=True)
    frappe.db.set_value(
        "NDIS Sandbox Payment Entry Run",
        sandbox_run,
        {"status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "validation_log": reason or "Sandbox Payment Entry run cancelled."},
        update_modified=False,
    )
    frappe.db.sql("UPDATE `tabNDIS Sandbox Payment Entry Run Line` SET status = 'Cancelled' WHERE sandbox_run = %(sandbox_run)s", {"sandbox_run": sandbox_run})
    frappe.db.commit()
    return {"sandbox_run": sandbox_run, "status": "Cancelled", "payment_entry": run.payment_entry, "note": "Sandbox run cancelled internally. Draft Payment Entry was not submitted and no GL/payment movement was created."}


def block_sandbox_payment_entry_submit(doc, method=None):
    if int(doc.get("custom_ndis_sandbox_payment_entry_draft_only") or 0):
        frappe.throw(_("This is an NDIS sandbox draft-only Payment Entry and cannot be submitted. No GL Entry or payment movement may be created from Phase 3C sandbox records."))
    if "NDIS SANDBOX DRAFT PAYMENT ENTRY ONLY" in (doc.get("remarks") or ""):
        frappe.throw(_("This Payment Entry is marked as NDIS SANDBOX DRAFT PAYMENT ENTRY ONLY and cannot be submitted."))


@frappe.whitelist()
def quick_sandbox_payment_entry_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Sandbox Payment Entry Run",
        fields=["name", "run_id", "status", "allocation_preview", "mapping_rule", "remittance_import", "payment_entry", "payment_entry_docstatus", "party", "company", "paid_amount", "received_amount", "included_line_count", "excluded_line_count", "duplicate_line_count", "blocker_count", "warning_count", "created_on"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Sandbox Payment Entry Run Line",
        fields=["name", "sandbox_run", "status", "line_no", "line_label", "sales_invoice", "customer", "allocation_amount", "source_status", "decision", "payment_entry_reference_created"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "draft_sandbox_payment_entries": frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0}),
        "submitted_sandbox_payment_entries": frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1}),
        "submitted_payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
    }
    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement": SANDBOX_PE_ACK,
        "draft_only_confirmation": DRAFT_ONLY_CONFIRMATION,
        "note": "Sandbox summary only. Draft Payment Entries may exist, but no submitted Payment Entry, GL Entry, Journal Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement should be created.",
    }


def execute_sandbox_payment_entry_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["status", "allocation_preview", "payment_entry"]:
        if filters.get(fieldname):
            conditions.append(f"r.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    if filters.get("from_date"):
        conditions.append("DATE(r.created_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.created_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run", "width": 220},
        {"fieldname": "run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 290},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "allocation_preview", "label": _("Allocation Preview"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "width": 220},
        {"fieldname": "payment_entry", "label": _("Draft Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 190},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "party", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "paid_amount", "label": _("Paid Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "included_line_count", "label": _("Included"), "fieldtype": "Int", "width": 90},
        {"fieldname": "excluded_line_count", "label": _("Excluded"), "fieldtype": "Int", "width": 90},
        {"fieldname": "duplicate_line_count", "label": _("Duplicates"), "fieldtype": "Int", "width": 100},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS sandbox_run, r.run_id, r.status, r.allocation_preview, r.payment_entry,
            r.payment_entry_docstatus, r.party, r.paid_amount, r.included_line_count,
            r.excluded_line_count, r.duplicate_line_count, r.blocker_count, r.warning_count,
            r.created_on, %(currency)s AS currency
        FROM `tabNDIS Sandbox Payment Entry Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.run_id for row in data[:20]], "datasets": [{"name": "Paid Amount", "values": [flt(row.paid_amount) for row in data[:20]]}, {"name": "Included Lines", "values": [int(row.included_line_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runs"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Created Draft Payment Entry"]), "indicator": "Green", "label": _("Draft PEs Created"), "datatype": "Int"},
        {"value": len([row for row in data if int(row.payment_entry_docstatus or 0) == 1]), "indicator": "Red", "label": _("Submitted PEs"), "datatype": "Int"},
        {"value": sum(flt(row.paid_amount) for row in data), "indicator": "Blue", "label": _("Total Draft Amount"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_sandbox_payment_entry_run_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["sandbox_run", "status", "sales_invoice", "customer"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run Line", "width": 220},
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_label", "label": _("Line Label"), "fieldtype": "Data", "width": 240},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "allocation_amount", "label": _("Allocation"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "source_status", "label": _("Source Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "decision", "label": _("Decision"), "fieldtype": "Data", "width": 260},
        {"fieldname": "block_reason", "label": _("Block Reason"), "fieldtype": "Small Text", "width": 360},
        {"fieldname": "payment_entry_reference_created", "label": _("PE Ref Created"), "fieldtype": "Check", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.sandbox_run, l.status, l.line_no, l.line_label, l.sales_invoice,
            l.customer, l.allocation_amount, l.outstanding_amount, l.source_status,
            l.decision, l.block_reason, l.payment_entry_reference_created, %(currency)s AS currency
        FROM `tabNDIS Sandbox Payment Entry Run Line` l
        {build_where(conditions)}
        ORDER BY l.creation DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Excluded"] = chart_map.get(row.status or "Excluded", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Included In Draft PE"]), "indicator": "Green", "label": _("Included"), "datatype": "Int"},
        {"value": sum(flt(row.allocation_amount) for row in data), "indicator": "Blue", "label": _("Allocation Amount"), "datatype": "Currency", "currency": currency()},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
