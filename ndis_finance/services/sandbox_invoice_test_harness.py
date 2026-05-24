import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SUBMITTED_SANDBOX_INVOICE_ACK = "I_CONFIRM_CREATE_SUBMITTED_SANDBOX_SALES_INVOICE_WITH_STANDARD_ERP_GL"


def make_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-SI-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def validate_sandbox_config(submit_invoice=0):
    errors = []
    warnings = []
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)

    if not sandbox_enabled:
        errors.append("Site config ndis_finance_sandbox_posting_enabled is not enabled.")

    if production_mode:
        errors.append("Site config ndis_finance_production_mode is enabled.")

    site = frappe.local.site or ""
    local_ok = "localhost" in site or site.startswith("dev.") or site.startswith("test.") or site.startswith("hexflow.")

    if int(submit_invoice or 0) and not local_ok and not int(frappe.conf.get("ndis_finance_allow_non_local_sandbox_invoice_submit") or 0):
        errors.append("Submitted sandbox invoice creation is only allowed on localhost/dev/test unless override is enabled.")

    return {
        "sandbox_enabled": sandbox_enabled,
        "production_mode": production_mode,
        "local_site_ok": local_ok,
        "errors": errors,
        "warnings": warnings,
    }


def get_company(company=None):
    if company and frappe.db.exists("Company", company):
        return company

    default_company = frappe.defaults.get_user_default("Company")
    if default_company and frappe.db.exists("Company", default_company):
        return default_company

    row = frappe.get_all("Company", fields=["name"], order_by="creation asc", limit=1)
    if row:
        return row[0].name

    frappe.throw(_("No Company found."))


def find_account(company, root_type=None, account_type=None):
    filters = {"company": company, "is_group": 0, "disabled": 0}

    if root_type:
        filters["root_type"] = root_type

    if account_type:
        filters["account_type"] = account_type

    rows = frappe.get_all("Account", filters=filters, fields=["name"], order_by="lft asc", limit=1)
    return rows[0].name if rows else None


def validate_account(account, company):
    if not account or not frappe.db.exists("Account", account):
        frappe.throw(_("Account does not exist: {0}").format(account))

    doc = frappe.get_doc("Account", account)

    if int(doc.is_group or 0):
        frappe.throw(_("Account is group account: {0}").format(account))

    if doc.company != company:
        frappe.throw(_("Account {0} does not belong to company {1}.").format(account, company))

    return True


def find_receivable_account(company, provided=None):
    if provided:
        validate_account(provided, company)
        return provided

    account = find_account(company, root_type="Asset", account_type="Receivable")
    if account:
        return account

    account = find_account(company, root_type="Asset")
    if account:
        return account

    frappe.throw(_("No non-group Asset/Receivable account found for company {0}.").format(company))


def find_income_account(company, provided=None):
    if provided:
        validate_account(provided, company)
        return provided

    account = find_account(company, root_type="Income")
    if account:
        return account

    frappe.throw(_("No non-group Income account found for company {0}.").format(company))


def find_cost_center(company, provided=None):
    if provided:
        if not frappe.db.exists("Cost Center", provided):
            frappe.throw(_("Cost Center does not exist: {0}").format(provided))
        return provided

    rows = frappe.get_all(
        "Cost Center",
        filters={"company": company, "is_group": 0, "disabled": 0},
        fields=["name"],
        order_by="lft asc",
        limit=1,
    )
    return rows[0].name if rows else None


def find_item_group():
    if frappe.db.exists("Item Group", "Services"):
        return "Services"

    row = frappe.get_all("Item Group", filters={"is_group": 0}, fields=["name"], limit=1)
    if row:
        return row[0].name

    frappe.throw(_("No Item Group found."))


def find_uom():
    if frappe.db.exists("UOM", "Nos"):
        return "Nos"

    row = frappe.get_all("UOM", fields=["name"], limit=1)
    if row:
        return row[0].name

    frappe.throw(_("No UOM found."))


def find_customer_group():
    if frappe.db.exists("Customer Group", "Individual"):
        return "Individual"

    row = frappe.get_all("Customer Group", filters={"is_group": 0}, fields=["name"], limit=1)
    return row[0].name if row else None


def find_territory():
    if frappe.db.exists("Territory", "Australia"):
        return "Australia"

    if frappe.db.exists("Territory", "All Territories"):
        return "All Territories"

    row = frappe.get_all("Territory", filters={"is_group": 0}, fields=["name"], limit=1)
    return row[0].name if row else None


def get_default_price_list():
    price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
    if price_list and frappe.db.exists("Price List", price_list):
        return price_list

    row = frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, fields=["name"], limit=1)
    return row[0].name if row else None


def get_gl_count_for_invoice(sales_invoice):
    if not sales_invoice or not frappe.db.exists("DocType", "GL Entry"):
        return 0

    return frappe.db.count("GL Entry", {"voucher_type": "Sales Invoice", "voucher_no": sales_invoice})


def unrelated_gl_today(exclude_sales_invoice=None):
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0

    if exclude_sales_invoice:
        return frappe.db.count("GL Entry", {"creation": [">=", today()], "voucher_no": ["!=", exclude_sales_invoice]})

    return frappe.db.count("GL Entry", {"creation": [">=", today()]})


def create_or_get_customer(run_name=None):
    customer_name = "NDIS Sandbox Customer - Phase 4A"
    existing = frappe.db.exists("Customer", {"customer_name": customer_name})

    if existing:
        customer = frappe.get_doc("Customer", existing)
        if customer.meta.has_field("custom_ndis_sandbox_customer"):
            customer.custom_ndis_sandbox_customer = 1
        if customer.meta.has_field("custom_ndis_sandbox_invoice_test_run") and run_name:
            customer.custom_ndis_sandbox_invoice_test_run = run_name
        customer.save(ignore_permissions=True)
        return customer.name, "Reused"

    customer = frappe.new_doc("Customer")
    customer.customer_name = customer_name
    customer.customer_type = "Individual"

    customer_group = find_customer_group()
    if customer_group:
        customer.customer_group = customer_group

    territory = find_territory()
    if territory:
        customer.territory = territory

    if customer.meta.has_field("custom_ndis_sandbox_customer"):
        customer.custom_ndis_sandbox_customer = 1

    if customer.meta.has_field("custom_ndis_sandbox_invoice_test_run") and run_name:
        customer.custom_ndis_sandbox_invoice_test_run = run_name

    customer.insert(ignore_permissions=True)
    return customer.name, "Created"


def create_or_get_item(run_name=None, rate=100, income_account=None):
    item_code = "NDIS-SANDBOX-SERVICE-PHASE4A"

    if frappe.db.exists("Item", item_code):
        item = frappe.get_doc("Item", item_code)
        if item.meta.has_field("custom_ndis_sandbox_item"):
            item.custom_ndis_sandbox_item = 1
        if item.meta.has_field("custom_ndis_sandbox_invoice_test_run") and run_name:
            item.custom_ndis_sandbox_invoice_test_run = run_name
        item.save(ignore_permissions=True)
        return item.name, "Reused"

    item = frappe.new_doc("Item")
    item.item_code = item_code
    item.item_name = "NDIS Sandbox Service Phase 4A"
    item.item_group = find_item_group()
    item.stock_uom = find_uom()
    item.is_stock_item = 0
    item.standard_rate = flt(rate or 100)

    if item.meta.has_field("include_item_in_manufacturing"):
        item.include_item_in_manufacturing = 0

    if income_account and item.meta.has_field("income_account"):
        item.income_account = income_account

    if item.meta.has_field("custom_ndis_sandbox_item"):
        item.custom_ndis_sandbox_item = 1

    if item.meta.has_field("custom_ndis_sandbox_invoice_test_run") and run_name:
        item.custom_ndis_sandbox_invoice_test_run = run_name

    item.insert(ignore_permissions=True)
    return item.name, "Created"


def create_test_run(status, test_mode, company, invoice_amount, acknowledgement, notes=None, validation=None):
    run = frappe.new_doc("NDIS Sandbox Invoice Test Run")
    run.run_id = make_run_id()
    run.status = status
    run.test_mode = test_mode
    run.sandbox_only = 1
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    run.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    run.company = company
    run.invoice_amount = flt(invoice_amount or 100)
    run.currency = currency(company)
    run.required_acknowledgement = SUBMITTED_SANDBOX_INVOICE_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(acknowledgement == SUBMITTED_SANDBOX_INVOICE_ACK)
    run.expected_gl_from_submitted_invoice = 1 if test_mode == "Submitted Sandbox Invoice" else 0
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation or {})
    run.notes = notes
    run.insert(ignore_permissions=True)
    return run


def add_run_line(run, status, record_doctype, record_name, docstatus=0, amount=0, gl_entry_count=0, action_taken=None):
    line = frappe.new_doc("NDIS Sandbox Invoice Test Line")
    line.test_run = run.name
    line.status = status
    line.line_no = frappe.db.count("NDIS Sandbox Invoice Test Line", {"test_run": run.name}) + 1
    line.record_doctype = record_doctype
    line.record_name = record_name
    line.record_docstatus = int(docstatus or 0)
    line.amount = flt(amount or 0)
    line.gl_entry_count = int(gl_entry_count or 0)
    line.action_taken = action_taken
    line.insert(ignore_permissions=True)
    return line


def create_sales_invoice(run, customer, item, company, receivable_account, income_account, cost_center, amount, acknowledgement=None):
    invoice = frappe.new_doc("Sales Invoice")
    invoice.company = company
    invoice.customer = customer
    invoice.posting_date = today()
    invoice.due_date = add_days(today(), 7)
    invoice.debit_to = receivable_account
    invoice.currency = currency(company)

    price_list = get_default_price_list()
    if price_list:
        invoice.selling_price_list = price_list

    if invoice.meta.has_field("custom_ndis_sandbox_test_invoice"):
        invoice.custom_ndis_sandbox_test_invoice = 1

    if invoice.meta.has_field("custom_ndis_sandbox_invoice_test_run"):
        invoice.custom_ndis_sandbox_invoice_test_run = run.name

    if invoice.meta.has_field("custom_ndis_sandbox_invoice_acknowledgement"):
        invoice.custom_ndis_sandbox_invoice_acknowledgement = acknowledgement

    invoice.remarks = (
        "NDIS SANDBOX SALES INVOICE TEST DATA ONLY. "
        f"Created by {run.name}. "
        "Do not mix with production customers, remittances or Payment Entries."
    )
    row = {
        "item_code": item,
        "qty": 1,
        "rate": flt(amount or 100),
        "amount": flt(amount or 100),
        "income_account": income_account,
    }

    if cost_center:
        row["cost_center"] = cost_center

    invoice.append("items", row)
    invoice.insert(ignore_permissions=True)
    return invoice


@frappe.whitelist()
def create_sandbox_invoice_test_data(
    submit_invoice=0,
    acknowledgement=None,
    company=None,
    receivable_account=None,
    income_account=None,
    cost_center=None,
    invoice_amount=100,
    dry_run=1,
    notes=None,
):
    assert_action("create_sandbox_invoice_test_data")

    company = get_company(company)
    submit_invoice = int(submit_invoice or 0)
    invoice_amount = flt(invoice_amount or 100)
    test_mode = "Submitted Sandbox Invoice" if submit_invoice else "Draft Invoice Only"
    sandbox_config = validate_sandbox_config(submit_invoice=submit_invoice)
    errors = list(sandbox_config.get("errors") or [])
    warnings = list(sandbox_config.get("warnings") or [])

    if submit_invoice and acknowledgement != SUBMITTED_SANDBOX_INVOICE_ACK:
        errors.append(f"Invalid acknowledgement. Required: {SUBMITTED_SANDBOX_INVOICE_ACK}")

    if invoice_amount <= 0:
        errors.append("Invoice amount must be positive.")

    try:
        receivable_account = find_receivable_account(company, receivable_account)
    except Exception as exc:
        errors.append(str(exc))

    try:
        income_account = find_income_account(company, income_account)
    except Exception as exc:
        errors.append(str(exc))

    try:
        cost_center = find_cost_center(company, cost_center)
    except Exception as exc:
        warnings.append(str(exc))
        cost_center = None

    validation = {
        "submit_invoice": submit_invoice,
        "test_mode": test_mode,
        "company": company,
        "receivable_account": receivable_account,
        "income_account": income_account,
        "cost_center": cost_center,
        "invoice_amount": invoice_amount,
        "sandbox_config": sandbox_config,
        "errors": errors,
        "warnings": warnings,
        "required_acknowledgement": SUBMITTED_SANDBOX_INVOICE_ACK,
        "note": "Dry-run only. No Customer, Item, Sales Invoice or GL Entry created." if int(dry_run or 0) else "Sandbox invoice test-data creation requested.",
    }

    if int(dry_run or 0):
        return validation

    if errors:
        run = create_test_run("Blocked", test_mode, company, invoice_amount, acknowledgement, notes=notes, validation=validation)
        frappe.db.commit()
        validation["created"] = False
        validation["test_run"] = run.name
        validation["status"] = "Blocked"
        return validation

    run = create_test_run("Draft", test_mode, company, invoice_amount, acknowledgement, notes=notes, validation=validation)
    customer, customer_action = create_or_get_customer(run_name=run.name)
    item, item_action = create_or_get_item(run_name=run.name, rate=invoice_amount, income_account=income_account)

    add_run_line(run, customer_action, "Customer", customer, docstatus=0, amount=0, action_taken=f"{customer_action} sandbox customer.")
    add_run_line(run, item_action, "Item", item, docstatus=0, amount=0, action_taken=f"{item_action} sandbox service item.")

    invoice = create_sales_invoice(
        run=run,
        customer=customer,
        item=item,
        company=company,
        receivable_account=receivable_account,
        income_account=income_account,
        cost_center=cost_center,
        amount=invoice_amount,
        acknowledgement=acknowledgement,
    )

    if submit_invoice:
        invoice.submit()
        invoice.reload()
        status = "Submitted Invoice Created"
        line_status = "Submitted"
    else:
        status = "Created Draft Invoice"
        line_status = "Created"

    gl_count = get_gl_count_for_invoice(invoice.name)
    add_run_line(
        run,
        line_status,
        "Sales Invoice",
        invoice.name,
        docstatus=invoice.docstatus,
        amount=invoice.grand_total,
        gl_entry_count=gl_count,
        action_taken="Submitted sandbox Sales Invoice with standard ERPNext GL." if submit_invoice else "Created draft sandbox Sales Invoice only.",
    )
    frappe.db.set_value(
        "NDIS Sandbox Invoice Test Run",
        run.name,
        {
            "status": status,
            "customer": customer,
            "item": item,
            "sales_invoice": invoice.name,
            "sales_invoice_docstatus": invoice.docstatus,
            "sales_invoice_outstanding_amount": invoice.outstanding_amount,
            "receivable_account": receivable_account,
            "income_account": income_account,
            "cost_center": cost_center,
            "linked_gl_entry_count": gl_count,
            "unrelated_gl_entry_count_today": unrelated_gl_today(exclude_sales_invoice=invoice.name),
            "validation_log": safe_json(validation),
        },
        update_modified=False,
    )
    frappe.db.commit()

    return {
        "created": True,
        "test_run": run.name,
        "run_id": run.run_id,
        "status": status,
        "test_mode": test_mode,
        "customer": customer,
        "item": item,
        "sales_invoice": invoice.name,
        "sales_invoice_docstatus": invoice.docstatus,
        "outstanding_amount": invoice.outstanding_amount,
        "linked_gl_entry_count": gl_count,
        "expected_gl_from_submitted_invoice": 1 if submit_invoice else 0,
        "unrelated_gl_entry_count_today": unrelated_gl_today(exclude_sales_invoice=invoice.name),
        "note": "Sandbox test invoice created. No Payment Entry, Journal Entry, Purchase Invoice, payroll, STP, ABA, email, bank allocation or Xero export was created.",
    }


@frappe.whitelist()
def cancel_sandbox_invoice_test_run(test_run, reason=None):
    assert_action("cancel_sandbox_invoice_test_run")

    if not frappe.db.exists("NDIS Sandbox Invoice Test Run", test_run):
        frappe.throw(_("Sandbox Invoice Test Run not found: {0}").format(test_run))

    run = frappe.get_doc("NDIS Sandbox Invoice Test Run", test_run)
    frappe.db.set_value(
        "NDIS Sandbox Invoice Test Run",
        test_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "validation_log": reason or "Sandbox invoice test run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Sandbox Invoice Test Line`
        SET status = 'Cancelled'
        WHERE test_run = %(test_run)s
        AND status NOT IN ('Submitted')
        """,
        {"test_run": test_run},
    )
    frappe.db.commit()

    return {
        "test_run": test_run,
        "status": "Cancelled",
        "sales_invoice": run.sales_invoice,
        "note": "Test run cancelled as an audit state only. It does not cancel/delete submitted Sales Invoice or GL. Cleanup/cancellation should be handled by a later dedicated phase.",
    }


def block_unacknowledged_sandbox_sales_invoice_submit(doc, method=None):
    if int(doc.get("custom_ndis_sandbox_test_invoice") or 0):
        ack = doc.get("custom_ndis_sandbox_invoice_acknowledgement")
        if ack != SUBMITTED_SANDBOX_INVOICE_ACK:
            frappe.throw(
                _("Sandbox Sales Invoice submission blocked. Required acknowledgement: {0}").format(
                    SUBMITTED_SANDBOX_INVOICE_ACK
                )
            )


@frappe.whitelist()
def quick_sandbox_invoice_test_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Sandbox Invoice Test Run",
        fields=[
            "name",
            "run_id",
            "status",
            "test_mode",
            "company",
            "customer",
            "item",
            "sales_invoice",
            "sales_invoice_docstatus",
            "sales_invoice_outstanding_amount",
            "linked_gl_entry_count",
            "unrelated_gl_entry_count_today",
            "created_on",
            "created_by_user",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Sandbox Invoice Test Line",
        fields=["name", "test_run", "status", "record_doctype", "record_name", "record_docstatus", "amount", "gl_entry_count", "action_taken"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "sandbox_sales_invoices": frappe.db.count("Sales Invoice", {"custom_ndis_sandbox_test_invoice": 1}),
        "submitted_sandbox_sales_invoices": frappe.db.count("Sales Invoice", {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 1}),
        "payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
        "submitted_payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Payment Entry") else 0,
        "submitted_journal_entries_today": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "purchase_invoices_today": frappe.db.count("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }
    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement_for_submitted_invoice": SUBMITTED_SANDBOX_INVOICE_ACK,
        "note": "Sandbox invoice test-data summary only. Submitted sandbox Sales Invoice may have standard ERPNext GL. No Payment Entry, JE, Purchase Invoice, payroll, STP, ABA, email, bank allocation or Xero export should be created by Phase 4A.",
    }


def execute_test_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key, column in [
        ("status", "r.status"),
        ("test_mode", "r.test_mode"),
        ("sales_invoice", "r.sales_invoice"),
    ]:
        if filters.get(key):
            conditions.append(f"{column} = %({key})s")
            params[key] = filters.get(key)

    if filters.get("from_date"):
        conditions.append("DATE(r.created_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions.append("DATE(r.created_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    params["currency"] = currency()
    columns = [
        {"fieldname": "test_run", "label": _("Test Run"), "fieldtype": "Link", "options": "NDIS Sandbox Invoice Test Run", "width": 220},
        {"fieldname": "run_id", "label": _("Run ID"), "fieldtype": "Data", "width": 280},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "test_mode", "label": _("Test Mode"), "fieldtype": "Data", "width": 190},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 190},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "sales_invoice_docstatus", "label": _("SI Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "sales_invoice_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "linked_gl_entry_count", "label": _("Linked GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "unrelated_gl_entry_count_today", "label": _("Unrelated GL Today"), "fieldtype": "Int", "width": 140},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS test_run,
            r.run_id,
            r.status,
            r.test_mode,
            r.company,
            r.customer,
            r.sales_invoice,
            r.sales_invoice_docstatus,
            r.sales_invoice_outstanding_amount,
            r.linked_gl_entry_count,
            r.unrelated_gl_entry_count_today,
            r.created_on,
            %(currency)s AS currency
        FROM `tabNDIS Sandbox Invoice Test Run` r
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
                {"name": "Outstanding", "values": [flt(row.sales_invoice_outstanding_amount) for row in data[:20]]},
                {"name": "Linked GL", "values": [int(row.linked_gl_entry_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Runs"), "datatype": "Int"},
        {"value": len([row for row in data if row.sales_invoice_docstatus == 1]), "indicator": "Green", "label": _("Submitted Sandbox SIs"), "datatype": "Int"},
        {"value": sum(flt(row.sales_invoice_outstanding_amount) for row in data), "indicator": "Blue", "label": _("Outstanding"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.linked_gl_entry_count or 0) for row in data), "indicator": "Orange", "label": _("Linked GL Entries"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_test_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key, column in [
        ("test_run", "l.test_run"),
        ("status", "l.status"),
        ("record_doctype", "l.record_doctype"),
    ]:
        if filters.get(key):
            conditions.append(f"{column} = %({key})s")
            params[key] = filters.get(key)

    params["currency"] = currency()
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Sandbox Invoice Test Line", "width": 220},
        {"fieldname": "test_run", "label": _("Test Run"), "fieldtype": "Link", "options": "NDIS Sandbox Invoice Test Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "record_doctype", "label": _("Record DocType"), "fieldtype": "Data", "width": 160},
        {"fieldname": "record_name", "label": _("Record Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "record_docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 90},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "gl_entry_count", "label": _("GL Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "action_taken", "label": _("Action Taken"), "fieldtype": "Small Text", "width": 400},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.test_run,
            l.status,
            l.record_doctype,
            l.record_name,
            l.record_docstatus,
            l.amount,
            l.gl_entry_count,
            l.action_taken,
            %(currency)s AS currency
        FROM `tabNDIS Sandbox Invoice Test Line` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.record_doctype or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1

    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Records", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Submitted"]), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(flt(row.amount) for row in data), "indicator": "Blue", "label": _("Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.gl_entry_count or 0) for row in data), "indicator": "Orange", "label": _("GL Count"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
