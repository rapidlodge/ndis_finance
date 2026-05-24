import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.payment_entry_sandbox_design import create_payment_entry_allocation_preview
from ndis_finance.services.permissions import assert_action
from ndis_finance.services.sandbox_payment_entry_posting import (
    SANDBOX_PE_ACK,
    create_sandbox_payment_entry_draft,
)


SMOKE_ACK = "I_CONFIRM_RUN_INVOICE_BACKED_SANDBOX_PAYMENT_ENTRY_SMOKE"
MAPPING_RULE = "NDIS-PE-MAP-NDIA-DIRECT"


def make_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-INV-PE-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def currency(company=None):
    if company and frappe.db.exists("Company", company):
        value = frappe.db.get_value("Company", company, "default_currency")
        if value:
            return value
    return frappe.defaults.get_global_default("currency") or "AUD"


def validate_sandbox_config():
    errors = []
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)

    if not sandbox_enabled:
        errors.append("Site config ndis_finance_sandbox_posting_enabled is not enabled.")

    if production_mode:
        errors.append("Site config ndis_finance_production_mode is enabled.")

    return {
        "sandbox_enabled": sandbox_enabled,
        "production_mode": production_mode,
        "errors": errors,
    }


def add_line(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None, amount=0):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "source_doctype": source_doctype,
            "source_name": source_name,
            "amount": flt(amount or 0),
        }
    )


def get_gl_count(voucher_type, voucher_no):
    if not voucher_no or not frappe.db.exists("DocType", "GL Entry"):
        return 0

    return frappe.db.count("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})


def find_submitted_sandbox_invoice(sales_invoice=None):
    filters = {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 1}

    if sales_invoice:
        filters["name"] = sales_invoice

    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "company",
            "customer",
            "debit_to",
            "outstanding_amount",
            "docstatus",
            "currency",
            "custom_ndis_sandbox_invoice_test_run",
        ],
        order_by="creation desc",
        limit=1,
    )

    if not rows:
        frappe.throw(_("No submitted sandbox Sales Invoice found. Complete Phase 4A submitted sandbox invoice test first."))

    row = rows[0]

    if flt(row.outstanding_amount) <= 0:
        frappe.throw(_("Submitted sandbox Sales Invoice has no outstanding amount: {0}").format(row.name))

    return frappe._dict(row)


def validate_account(account, company):
    if not account or not frappe.db.exists("Account", account):
        frappe.throw(_("Account does not exist: {0}").format(account))

    doc = frappe.get_doc("Account", account)

    if int(doc.is_group or 0):
        frappe.throw(_("Account is a group account: {0}").format(account))

    if doc.company != company:
        frappe.throw(_("Account {0} does not belong to company {1}.").format(account, company))

    return True


def find_bank_account(company, provided=None):
    if provided:
        validate_account(provided, company)
        return provided

    for filters in [
        {"company": company, "is_group": 0, "disabled": 0, "account_type": "Bank"},
        {"company": company, "is_group": 0, "disabled": 0, "account_type": "Cash"},
        {"company": company, "is_group": 0, "disabled": 0, "root_type": "Asset"},
    ]:
        rows = frappe.get_all("Account", filters=filters, fields=["name"], order_by="lft asc", limit=1)
        if rows:
            return rows[0].name

    frappe.throw(_("No non-group Bank/Cash/Asset account found for company {0}.").format(company))


def get_remittance_parentfield():
    parent_meta = frappe.get_meta("NDIS Remittance Import")
    for df in parent_meta.fields:
        if df.fieldtype == "Table" and df.options == "NDIS Remittance Import Line":
            return df.fieldname
    return "lines"


def set_if_has(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def set_link_if_exists(doc, fieldname, value):
    if not doc.meta.has_field(fieldname):
        return

    df = doc.meta.get_field(fieldname)
    if df.fieldtype != "Link" or frappe.db.exists(df.options, value):
        setattr(doc, fieldname, value)


def set_select_safe(doc, fieldname, preferred_values):
    if not doc.meta.has_field(fieldname):
        return

    df = doc.meta.get_field(fieldname)
    options = [opt.strip() for opt in (df.options or "").split("\n") if opt.strip()]

    for preferred in preferred_values:
        if not options or preferred in options:
            setattr(doc, fieldname, preferred)
            return

    if options:
        setattr(doc, fieldname, options[0])


def create_smoke_remittance_import(invoice, run_name):
    doc = frappe.new_doc("NDIS Remittance Import")
    amount = flt(invoice.outstanding_amount)

    set_if_has(doc, "remittance_import_id", f"{run_name}-REMIT")
    set_if_has(doc, "title", f"Phase 4B Invoice-backed PE Smoke - {invoice.name}")
    set_if_has(doc, "company", invoice.company)
    set_if_has(doc, "posting_date", today())
    set_if_has(doc, "import_date", today())
    set_if_has(doc, "received_date", today())
    set_if_has(doc, "payment_date", today())
    set_if_has(doc, "reference_no", run_name)
    set_if_has(doc, "remittance_reference", run_name)
    set_if_has(doc, "source_reference", run_name)
    set_if_has(doc, "external_payment_reference", run_name)
    set_if_has(doc, "total_received_amount", amount)
    set_if_has(doc, "expected_claim_amount", amount)
    set_if_has(doc, "received_amount", amount)
    set_if_has(doc, "allocated_amount", amount)
    set_if_has(doc, "matched_amount", amount)
    set_if_has(doc, "total_amount", amount)
    set_if_has(doc, "line_count", 1)
    set_if_has(doc, "matched_line_count", 1)
    set_if_has(doc, "imported_on", now_datetime())
    set_if_has(doc, "imported_by", frappe.session.user)
    set_if_has(doc, "notes", "Phase 4B sandbox remittance import for invoice-backed draft Payment Entry smoke test.")
    set_if_has(doc, "remarks", "Phase 4B sandbox remittance import only.")
    set_select_safe(doc, "status", ["Imported", "Matched", "Draft", "Open"])
    set_select_safe(doc, "import_status", ["Imported", "Matched", "Draft", "Open"])

    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc.name


def create_smoke_remittance_line(remittance_import, invoice, run_name):
    line = frappe.new_doc("NDIS Remittance Import Line")
    amount = flt(invoice.outstanding_amount)
    line_meta = frappe.get_meta("NDIS Remittance Import Line")

    if getattr(line_meta, "istable", 0):
        line.parent = remittance_import
        line.parenttype = "NDIS Remittance Import"
        line.parentfield = get_remittance_parentfield()

    set_if_has(line, "remittance_import", remittance_import)
    set_if_has(line, "line_label", f"Phase 4B Smoke Line - {invoice.name}")
    set_if_has(line, "invoice_number", invoice.name)
    set_if_has(line, "invoice_no", invoice.name)
    set_if_has(line, "invoice_reference", invoice.name)
    set_if_has(line, "sales_invoice", invoice.name)
    set_if_has(line, "invoice", invoice.name)
    set_if_has(line, "invoice_name", invoice.name)
    set_if_has(line, "sales_invoice_name", invoice.name)
    set_if_has(line, "reference_invoice", invoice.name)
    set_if_has(line, "erpnext_invoice", invoice.name)
    set_if_has(line, "claim_line", f"PHASE4B-SMOKE-{invoice.name}")
    set_if_has(line, "ndis_claim_line", f"PHASE4B-SMOKE-{invoice.name}")
    set_if_has(line, "claim_reference", f"PHASE4B-SMOKE-{invoice.name}")
    set_if_has(line, "external_claim_reference", f"PHASE4B-SMOKE-{invoice.name}")
    set_if_has(line, "paid_amount", amount)
    set_if_has(line, "received_amount", amount)
    set_if_has(line, "allocated_amount", amount)
    set_if_has(line, "payment_amount", amount)
    set_if_has(line, "amount_paid", amount)
    set_if_has(line, "amount", amount)
    set_if_has(line, "claim_amount", amount)
    set_if_has(line, "invoice_amount", amount)
    set_if_has(line, "participant_name", "Phase 4B Sandbox Participant")
    set_link_if_exists(line, "participant", "Phase 4B Sandbox Participant")
    set_if_has(line, "reference_no", run_name)
    set_if_has(line, "remittance_reference", run_name)
    set_if_has(line, "notes", "Phase 4B sandbox remittance line linked to submitted sandbox Sales Invoice.")
    set_select_safe(line, "outcome", ["Paid", "Matched", "Approved", "Successful"])
    set_select_safe(line, "payment_outcome", ["Paid", "Matched", "Approved", "Successful"])
    set_select_safe(line, "claim_outcome", ["Paid", "Matched", "Approved", "Successful"])
    set_select_safe(line, "claim_status", ["Paid", "Matched", "Approved", "Successful"])
    set_select_safe(line, "invoice_status", ["Paid", "Matched", "Approved", "Successful"])
    set_select_safe(line, "status", ["Paid", "Matched", "Imported", "Open"])

    line.insert(ignore_permissions=True, ignore_mandatory=True)
    return line.name


def create_smoke_run(status, invoice, acknowledgement, bank_account=None, validation=None, notes=None):
    run = frappe.new_doc("NDIS Invoice Backed PE Smoke Run")
    run.run_id = make_run_id()
    run.status = status
    run.smoke_mode = "Invoice-backed Draft PE"
    run.sandbox_only = 1
    run.sandbox_invoice_test_run = invoice.custom_ndis_sandbox_invoice_test_run
    run.sales_invoice = invoice.name
    run.sales_invoice_docstatus = invoice.docstatus
    run.sales_invoice_outstanding_amount = invoice.outstanding_amount
    run.sales_invoice_gl_entry_count = get_gl_count("Sales Invoice", invoice.name)
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    run.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    run.required_acknowledgement = SMOKE_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(acknowledgement == SMOKE_ACK)
    run.company = invoice.company
    run.customer = invoice.customer
    run.bank_account = bank_account
    run.receivable_account = invoice.debit_to
    run.smoke_amount = flt(invoice.outstanding_amount)
    run.currency = invoice.currency or currency(invoice.company)
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation or {})
    run.notes = notes
    run.insert(ignore_permissions=True)
    return run


def save_smoke_lines(run, items):
    for item in items:
        line = frappe.new_doc("NDIS Invoice Backed PE Smoke Line")
        line.smoke_run = run.name
        line.status = item["status"]
        line.severity = item["severity"]
        line.category = item["category"]
        line.check_key = item["check_key"]
        line.check_label = item["check_label"]
        line.detail = item["detail"]
        line.source_doctype = item.get("source_doctype")
        line.source_name = item.get("source_name")
        line.amount = flt(item.get("amount") or 0)
        line.checked_on = now_datetime()
        line.insert(ignore_permissions=True)


def submitted_pe_count_today():
    return frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1})


def summarise_items(items):
    return {
        "blocker_count": len([row for row in items if row["status"] == "Blocker"]),
        "warning_count": len([row for row in items if row["status"] == "Warning"]),
        "pass_count": len([row for row in items if row["status"] == "Pass"]),
        "info_count": len([row for row in items if row["status"] == "Info"]),
        "item_count": len(items),
    }


@frappe.whitelist()
def run_invoice_backed_pe_smoke(sales_invoice=None, bank_account=None, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_invoice_backed_pe_smoke")

    items = []
    sandbox_config = validate_sandbox_config()
    errors = list(sandbox_config["errors"])
    warnings = []

    if acknowledgement != SMOKE_ACK:
        errors.append(f"Invalid acknowledgement. Required: {SMOKE_ACK}")

    invoice = find_submitted_sandbox_invoice(sales_invoice=sales_invoice)

    try:
        bank_account = find_bank_account(invoice.company, bank_account)
    except Exception as exc:
        errors.append(str(exc))

    try:
        validate_account(invoice.debit_to, invoice.company)
    except Exception as exc:
        errors.append(str(exc))

    sales_invoice_gl_count = get_gl_count("Sales Invoice", invoice.name)

    if sales_invoice_gl_count <= 0:
        warnings.append("Submitted sandbox Sales Invoice has no GL Entry linked. This may indicate accounting settings are disabled.")

    add_line(
        items,
        "Pass",
        "Low",
        "Source Invoice",
        "submitted_sandbox_invoice",
        "Submitted sandbox Sales Invoice",
        f"Using submitted sandbox Sales Invoice {invoice.name} with outstanding amount {invoice.outstanding_amount}.",
        "Sales Invoice",
        invoice.name,
        invoice.outstanding_amount,
    )
    add_line(
        items,
        "Pass" if sales_invoice_gl_count else "Warning",
        "Low" if sales_invoice_gl_count else "Medium",
        "Source Invoice",
        "sales_invoice_gl",
        "Sales Invoice GL evidence",
        f"Linked Sales Invoice GL Entry count: {sales_invoice_gl_count}.",
        "Sales Invoice",
        invoice.name,
        invoice.outstanding_amount,
    )

    validation = {
        "dry_run": bool(int(dry_run or 0)),
        "sales_invoice": invoice.name,
        "company": invoice.company,
        "customer": invoice.customer,
        "receivable_account": invoice.debit_to,
        "bank_account": bank_account,
        "outstanding_amount": flt(invoice.outstanding_amount),
        "sales_invoice_gl_entry_count": sales_invoice_gl_count,
        "sandbox_config": sandbox_config,
        "errors": errors,
        "warnings": warnings,
        "required_acknowledgement": SMOKE_ACK,
        "note": "Dry-run only. No remittance, allocation preview, Payment Entry or GL created." if int(dry_run or 0) else "Invoice-backed sandbox PE smoke requested.",
    }

    if int(dry_run or 0):
        validation["items"] = items
        return validation

    if errors:
        for err in errors:
            add_line(items, "Blocker", "Critical", "Validation", "validation_error", "Validation error", err)

        run = create_smoke_run("Blocked", invoice, acknowledgement, bank_account=bank_account, validation=validation, notes=notes)
        save_smoke_lines(run, items)
        frappe.db.commit()
        validation.update({"created": False, "status": "Blocked", "smoke_run": run.name})
        return validation

    run = create_smoke_run("Validated", invoice, acknowledgement, bank_account=bank_account, validation=validation, notes=notes)

    try:
        remittance_import = create_smoke_remittance_import(invoice, run.name)
        remittance_line = create_smoke_remittance_line(remittance_import, invoice, run.name)

        add_line(items, "Pass", "Low", "Remittance", "remittance_import", "Smoke remittance import created", f"Created smoke remittance import {remittance_import}.", "NDIS Remittance Import", remittance_import, invoice.outstanding_amount)
        add_line(items, "Pass", "Low", "Remittance", "remittance_line", "Smoke remittance line created", f"Created smoke remittance line {remittance_line}.", "NDIS Remittance Import Line", remittance_line, invoice.outstanding_amount)

        preview_result = create_payment_entry_allocation_preview(
            remittance_import=remittance_import,
            mapping_rule=MAPPING_RULE,
            dry_run=0,
            notes="Phase 4B invoice-backed PE smoke allocation preview",
        )
        allocation_preview = preview_result.get("allocation_preview")
        allocatable_count = int((preview_result.get("summary") or {}).get("allocatable_line_count") or 0)

        if not allocation_preview or allocatable_count < 1:
            add_line(items, "Blocker", "Critical", "Allocation Preview", "allocatable_preview", "Allocatable preview line", "Allocation preview did not produce an allocatable line.", "NDIS Payment Entry Allocation Preview", allocation_preview, invoice.outstanding_amount)
            frappe.throw(_("Phase 4B allocation preview did not produce an allocatable line."))

        add_line(items, "Pass", "Low", "Allocation Preview", "allocatable_preview", "Allocatable preview line", f"Allocation preview {allocation_preview} created with {allocatable_count} allocatable line(s).", "NDIS Payment Entry Allocation Preview", allocation_preview, invoice.outstanding_amount)

        pe_result = create_sandbox_payment_entry_draft(
            allocation_preview=allocation_preview,
            acknowledgement=SANDBOX_PE_ACK,
            bank_account=bank_account,
            receivable_account=invoice.debit_to,
            fallback_customer=invoice.customer,
            dry_run=0,
            notes="Phase 4B invoice-backed sandbox draft Payment Entry smoke test",
        )
        payment_entry = pe_result.get("payment_entry")
        sandbox_pe_run = pe_result.get("sandbox_run")

        if not payment_entry:
            add_line(items, "Blocker", "Critical", "Draft Payment Entry", "payment_entry_created", "Sandbox draft Payment Entry created", "Phase 3C service did not return a Payment Entry.", "NDIS Sandbox Payment Entry Run", sandbox_pe_run, invoice.outstanding_amount)
            frappe.throw(_("Phase 3C sandbox Payment Entry service did not create a draft Payment Entry."))

        pe_docstatus = int(frappe.db.get_value("Payment Entry", payment_entry, "docstatus") or 0)
        pe_gl_count = get_gl_count("Payment Entry", payment_entry)
        submitted_pe_count = submitted_pe_count_today()

        add_line(
            items,
            "Pass" if pe_docstatus == 0 else "Blocker",
            "Low" if pe_docstatus == 0 else "Critical",
            "Draft Payment Entry",
            "payment_entry_docstatus",
            "Payment Entry is draft",
            f"Payment Entry {payment_entry} has docstatus {pe_docstatus}.",
            "Payment Entry",
            payment_entry,
            invoice.outstanding_amount,
        )
        add_line(
            items,
            "Pass" if pe_gl_count == 0 else "Blocker",
            "Low" if pe_gl_count == 0 else "Critical",
            "Payment Entry Guardrail",
            "payment_entry_gl",
            "Payment Entry GL count",
            f"Payment Entry {payment_entry} linked GL Entry count: {pe_gl_count}.",
            "Payment Entry",
            payment_entry,
            invoice.outstanding_amount,
        )
        add_line(
            items,
            "Pass" if submitted_pe_count == 0 else "Blocker",
            "Low" if submitted_pe_count == 0 else "Critical",
            "Payment Entry Guardrail",
            "submitted_pe_today",
            "Submitted Payment Entries today",
            f"Submitted Payment Entries today: {submitted_pe_count}.",
        )

        summary = summarise_items(items)
        status = "Completed" if summary["blocker_count"] == 0 else "Blocked"

        frappe.db.set_value(
            "NDIS Invoice Backed PE Smoke Run",
            run.name,
            {
                "status": status,
                "remittance_import": remittance_import,
                "remittance_import_line": remittance_line,
                "allocation_preview": allocation_preview,
                "sandbox_payment_entry_run": sandbox_pe_run,
                "payment_entry": payment_entry,
                "payment_entry_docstatus": pe_docstatus,
                "allocatable_line_count": allocatable_count,
                "allocation_preview_status": preview_result.get("status"),
                "allocation_preview_validation_status": preview_result.get("validation_status"),
                "payment_entry_gl_entry_count": pe_gl_count,
                "submitted_payment_entry_count": submitted_pe_count,
                "blocker_count": summary["blocker_count"],
                "warning_count": summary["warning_count"] + len(warnings),
                "validation_log": safe_json({**validation, "preview_result": preview_result, "pe_result": pe_result, "summary": summary}),
            },
            update_modified=False,
        )

        save_smoke_lines(run, items)
        frappe.db.commit()

        return {
            "created": True,
            "status": status,
            "smoke_run": run.name,
            "run_id": run.run_id,
            "sales_invoice": invoice.name,
            "remittance_import": remittance_import,
            "remittance_import_line": remittance_line,
            "allocation_preview": allocation_preview,
            "allocatable_line_count": allocatable_count,
            "sandbox_payment_entry_run": sandbox_pe_run,
            "payment_entry": payment_entry,
            "payment_entry_docstatus": pe_docstatus,
            "payment_entry_gl_entry_count": pe_gl_count,
            "submitted_payment_entry_count_today": submitted_pe_count,
            "summary": summary,
            "note": "Invoice-backed sandbox draft Payment Entry smoke completed. Payment Entry is draft only and has no linked GL.",
        }

    except Exception as exc:
        frappe.db.set_value("NDIS Invoice Backed PE Smoke Run", run.name, {"status": "Failed", "validation_log": safe_json({**validation, "error": str(exc)})}, update_modified=False)
        frappe.db.commit()
        raise


@frappe.whitelist()
def cancel_invoice_backed_pe_smoke(smoke_run, reason=None):
    assert_action("cancel_invoice_backed_pe_smoke")

    if not frappe.db.exists("NDIS Invoice Backed PE Smoke Run", smoke_run):
        frappe.throw(_("Invoice-backed PE Smoke Run not found: {0}").format(smoke_run))

    frappe.db.set_value(
        "NDIS Invoice Backed PE Smoke Run",
        smoke_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "validation_log": reason or "Invoice-backed PE smoke run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql("UPDATE `tabNDIS Invoice Backed PE Smoke Line` SET status = 'Cancelled' WHERE smoke_run = %(smoke_run)s", {"smoke_run": smoke_run})
    frappe.db.commit()

    return {
        "smoke_run": smoke_run,
        "status": "Cancelled",
        "note": "Smoke run cancelled as an audit state only. It does not delete remittance, allocation preview, draft Payment Entry, Sales Invoice or GL.",
    }


@frappe.whitelist()
def quick_invoice_backed_pe_smoke_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Invoice Backed PE Smoke Run",
        fields=[
            "name",
            "run_id",
            "status",
            "sales_invoice",
            "remittance_import",
            "allocation_preview",
            "sandbox_payment_entry_run",
            "payment_entry",
            "payment_entry_docstatus",
            "sales_invoice_outstanding_amount",
            "sales_invoice_gl_entry_count",
            "payment_entry_gl_entry_count",
            "submitted_payment_entry_count",
            "blocker_count",
            "warning_count",
            "created_on",
            "created_by_user",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Invoice Backed PE Smoke Line",
        fields=["name", "smoke_run", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name", "amount"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "draft_sandbox_payment_entries": frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0}),
        "submitted_sandbox_payment_entries": frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1}),
        "submitted_payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "payment_entry_gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "purchase_invoices_today": frappe.db.count("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
        "submitted_journal_entries_today": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
    }
    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement": SMOKE_ACK,
        "sandbox_pe_ack_used_in_phase3c": SANDBOX_PE_ACK,
        "note": "Invoice-backed PE smoke summary only. Draft sandbox Payment Entry may exist. No submitted Payment Entry or Payment Entry GL should exist.",
    }


def execute_smoke_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for fieldname in ["status", "sales_invoice", "payment_entry"]:
        if filters.get(fieldname):
            conditions.append(f"r.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    if filters.get("from_date"):
        conditions.append("DATE(r.created_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions.append("DATE(r.created_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    params["currency"] = frappe.defaults.get_global_default("currency") or "AUD"
    columns = [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Invoice Backed PE Smoke Run", "width": 220},
        {"fieldname": "run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 300},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "allocation_preview", "label": _("Allocation Preview"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "width": 220},
        {"fieldname": "payment_entry", "label": _("Draft Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 190},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "sales_invoice_outstanding_amount", "label": _("SI Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "sales_invoice_gl_entry_count", "label": _("SI GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_entry_count", "label": _("PE GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "submitted_payment_entry_count", "label": _("Submitted PE"), "fieldtype": "Int", "width": 110},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS smoke_run, r.run_id, r.status, r.sales_invoice, r.allocation_preview,
            r.payment_entry, r.payment_entry_docstatus, r.sales_invoice_outstanding_amount,
            r.sales_invoice_gl_entry_count, r.payment_entry_gl_entry_count,
            r.submitted_payment_entry_count, r.blocker_count, r.warning_count,
            r.created_on, %(currency)s AS currency
        FROM `tabNDIS Invoice Backed PE Smoke Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.run_id for row in data[:20]],
            "datasets": [
                {"name": "SI Outstanding", "values": [flt(row.sales_invoice_outstanding_amount) for row in data[:20]]},
                {"name": "PE GL", "values": [int(row.payment_entry_gl_entry_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Completed"]), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_entry_count or 0) for row in data), "indicator": "Red", "label": _("PE GL Count"), "datatype": "Int"},
        {"value": sum(int(row.submitted_payment_entry_count or 0) for row in data), "indicator": "Red", "label": _("Submitted PE Count"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_smoke_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for fieldname in ["smoke_run", "status", "category"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    params["currency"] = frappe.defaults.get_global_default("currency") or "AUD"
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Invoice Backed PE Smoke Line", "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": "NDIS Invoice Backed PE Smoke Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.smoke_run, l.status, l.severity, l.category,
            l.check_label, l.detail, l.source_doctype, l.source_name, l.amount,
            l.checked_on, %(currency)s AS currency
        FROM `tabNDIS Invoice Backed PE Smoke Line` l
        {build_where(conditions)}
        ORDER BY CASE l.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END,
            l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
