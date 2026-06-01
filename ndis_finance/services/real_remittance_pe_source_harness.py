import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS Real Remittance PE Source Harness Run"
LINE_DOCTYPE = "NDIS Real Remittance PE Source Harness Line"
HARNESS_ACK = "I_CONFIRM_PHASE6E_CREATE_CONTROLLED_ELIGIBLE_REMITTANCE_SOURCE_NO_PE"

HARNESS_CUSTOMER = "NDIS Real Remittance PE Harness Customer"
HARNESS_ITEM = "NDIS Real Remittance PE Harness Item"


def make_harness_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-SOURCE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def make_source_id(prefix):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Real Remittance PE Activation Gate",
        filters={
            "status": "Source Pending",
            "structural_ready_allowed": 1,
            "ready_for_real_smoke": 0,
            "real_posting_allowed": 0,
            "source_eligible_pending": 1,
        },
        fields=[
            "name",
            "activation_gate_id",
            "company",
            "bank_account",
            "receivable_account",
            "batch_line_cap",
            "batch_amount_cap",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def latest_design_scope():
    gate = latest_activation_gate()
    if gate:
        return gate
    rows = frappe.get_all(
        "NDIS Real Remittance PE Design Gate",
        filters={
            "status": "Approved",
            "design_approved_for_preview_phase": 1,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "company",
            "bank_account",
            "receivable_account",
            "batch_line_cap",
            "batch_amount_cap",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def get_single_value(doctype, filters=None, fieldname="name", order_by="creation asc"):
    rows = frappe.get_all(doctype, filters=filters or {}, fields=[fieldname], order_by=order_by, limit=1)
    return rows[0][fieldname] if rows else None


def ensure_customer():
    if frappe.db.exists("Customer", HARNESS_CUSTOMER):
        return HARNESS_CUSTOMER
    customer_group = get_single_value("Customer Group", {"is_group": 0}) or "All Customer Groups"
    territory = get_single_value("Territory", {"is_group": 0}) or "All Territories"
    doc = frappe.new_doc("Customer")
    doc.customer_name = HARNESS_CUSTOMER
    doc.customer_type = "Company"
    doc.customer_group = customer_group
    doc.territory = territory
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_item():
    if frappe.db.exists("Item", HARNESS_ITEM):
        return HARNESS_ITEM
    item_group = get_single_value("Item Group", {"is_group": 0}) or "All Item Groups"
    stock_uom = get_single_value("UOM") or "Nos"
    doc = frappe.new_doc("Item")
    doc.item_code = HARNESS_ITEM
    doc.item_name = HARNESS_ITEM
    doc.item_group = item_group
    doc.stock_uom = stock_uom
    doc.is_stock_item = 0
    doc.is_sales_item = 1
    doc.disabled = 0
    doc.description = "Controlled Phase 6E eligible remittance source harness item."
    doc.insert(ignore_permissions=True)
    return doc.name


def get_income_account(company):
    company_doc = frappe.get_doc("Company", company)
    if getattr(company_doc, "default_income_account", None):
        return company_doc.default_income_account
    for filters in (
        {"company": company, "root_type": "Income", "account_type": "Income Account", "is_group": 0, "disabled": 0},
        {"company": company, "root_type": "Income", "is_group": 0, "disabled": 0},
    ):
        account = get_single_value("Account", filters, order_by="name asc")
        if account:
            return account
    frappe.throw(_("Could not find income account for company {0}").format(company))


def get_cost_center(company):
    company_doc = frappe.get_doc("Company", company)
    if getattr(company_doc, "cost_center", None) and frappe.db.exists("Cost Center", company_doc.cost_center):
        return company_doc.cost_center
    cost_center = get_single_value("Cost Center", {"company": company, "is_group": 0, "disabled": 0}, order_by="name asc")
    if cost_center:
        return cost_center
    frappe.throw(_("Could not find cost center for company {0}").format(company))


def gl_count(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    return count_dt("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})


def gl_net(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    value = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
        FROM `tabGL Entry`
        WHERE voucher_type = %(voucher_type)s
        AND voucher_no = %(voucher_no)s
        """,
        {"voucher_type": voucher_type, "voucher_no": voucher_no},
    )[0][0]
    return flt(value, 2)


def set_if_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)
        return True
    return False


def select_option_value(doc, fieldname, desired):
    df = doc.meta.get_field(fieldname)
    if not df:
        return None
    if df.fieldtype != "Select" or not df.options:
        return desired
    options = [opt.strip() for opt in str(df.options).split("\n") if opt.strip()]
    desired_l = str(desired).lower()
    for option in options:
        if option.lower() == desired_l:
            return option
    for option in options:
        if desired_l in option.lower() or option.lower() in desired_l:
            return option
    return None


def set_first_field(doc, candidates, value):
    for fieldname in candidates:
        if not doc.meta.has_field(fieldname):
            continue
        val = select_option_value(doc, fieldname, value)
        if val is None:
            continue
        setattr(doc, fieldname, val)
        return fieldname
    return None


def add_harness_line(harness_run, record_type, record_doctype, record_name, label, status="Info", amount=0, detail=None):
    row = frappe.new_doc(LINE_DOCTYPE)
    row.harness_run = harness_run
    row.record_type = record_type
    row.record_doctype = record_doctype
    row.record_name = record_name
    row.record_label = label
    row.status = status
    row.amount = flt(amount or 0)
    row.detail = detail
    row.checked_on = now_datetime()
    row.insert(ignore_permissions=True)


def create_sales_invoice(run_name, company, receivable_account, amount):
    customer = ensure_customer()
    item = ensure_item()
    income_account = get_income_account(company)
    cost_center = get_cost_center(company)
    si = frappe.new_doc("Sales Invoice")
    si.company = company
    si.customer = customer
    si.posting_date = today()
    si.due_date = today()
    si.currency = currency()
    si.debit_to = receivable_account
    si.custom_ndis_real_remittance_pe_harness_invoice = 1
    si.custom_ndis_real_remittance_pe_harness_run = run_name
    si.remarks = "Controlled Phase 6E eligible remittance source harness invoice. Do not use for live operations."
    si.append(
        "items",
        {
            "item_code": item,
            "qty": 1,
            "rate": flt(amount),
            "income_account": income_account,
            "cost_center": cost_center,
            "description": "Controlled Phase 6E eligible remittance source harness item",
        },
    )
    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()
    return {
        "sales_invoice": si.name,
        "customer": customer,
        "item": item,
        "outstanding": flt(si.outstanding_amount),
        "gl_count": gl_count("Sales Invoice", si.name),
        "gl_net": gl_net("Sales Invoice", si.name),
    }


def create_claim_line(run_name, sales_invoice, company, amount):
    doc = frappe.new_doc("NDIS Claim Line")
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_source", 1)
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_run", run_name)
    set_first_field(doc, ["sales_invoice", "invoice", "sales_invoice_reference", "source_sales_invoice"], sales_invoice)
    sales_invoice_item = get_single_value("Sales Invoice Item", {"parent": sales_invoice}, fieldname="name")
    set_first_field(doc, ["sales_invoice_item", "invoice_item", "sales_invoice_detail"], sales_invoice_item)
    set_first_field(doc, ["company"], company)
    set_first_field(doc, ["claim_amount", "amount", "claimed_amount", "line_amount"], flt(amount))
    set_first_field(doc, ["paid_amount", "received_amount", "settled_amount"], 0)
    set_first_field(doc, ["claim_status", "status", "invoice_status"], "Submitted")
    set_first_field(doc, ["claim_outcome", "outcome", "payment_outcome"], "Pending")
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def create_remittance_import(run_name, company, amount):
    doc = frappe.new_doc("NDIS Remittance Import")
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_source", 1)
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_run", run_name)
    set_first_field(doc, ["remittance_import_id", "import_id", "ndis_remittance_import_id"], make_source_id("NDIS-6E-REMIT"))
    set_first_field(doc, ["company"], company)
    set_first_field(doc, ["import_date", "posting_date", "remittance_date", "payment_date"], today())
    set_first_field(doc, ["status", "import_status"], "Imported")
    set_first_field(doc, ["expected_claim_amount", "total_amount", "received_amount", "payment_amount", "allocated_amount"], flt(amount))
    set_first_field(doc, ["source_file", "file_name", "import_file"], "Phase 6E controlled eligible remittance source harness")
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def create_remittance_line(run_name, remittance_import, claim_line, sales_invoice, company, amount):
    line_meta = frappe.get_meta("NDIS Remittance Import Line")
    if int(line_meta.istable or 0):
        parent = frappe.get_doc("NDIS Remittance Import", remittance_import)
        table_field = None
        for df in parent.meta.fields:
            if df.fieldtype == "Table" and df.options == "NDIS Remittance Import Line":
                table_field = df.fieldname
                break
        if not table_field:
            frappe.throw(_("Could not find child table field for NDIS Remittance Import Line."))
        row = parent.append(table_field, {})
        populate_remittance_line(row, run_name, remittance_import, claim_line, sales_invoice, company, amount)
        parent.flags.ignore_mandatory = True
        parent.flags.ignore_links = True
        parent.save(ignore_permissions=True)
        return row.name
    doc = frappe.new_doc("NDIS Remittance Import Line")
    populate_remittance_line(doc, run_name, remittance_import, claim_line, sales_invoice, company, amount)
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def populate_remittance_line(doc, run_name, remittance_import, claim_line, sales_invoice, company, amount):
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_source", 1)
    set_if_field(doc, "custom_ndis_real_remittance_pe_harness_run", run_name)
    set_first_field(doc, ["remittance_import", "ndis_remittance_import", "import_reference"], remittance_import)
    set_first_field(doc, ["claim_outcome", "outcome", "payment_outcome", "invoice_status"], "Paid")
    set_first_field(doc, ["status"], "Paid")
    set_first_field(doc, ["match_status"], "Matched")
    set_first_field(doc, ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"], claim_line)
    set_first_field(doc, ["sales_invoice", "invoice", "invoice_reference", "sales_invoice_reference", "erpnext_sales_invoice"], sales_invoice)
    set_first_field(doc, ["company"], company)
    set_first_field(doc, ["paid_amount", "payment_amount", "received_amount", "amount", "allocated_amount"], flt(amount))
    set_first_field(doc, ["shortfall_amount", "variance_amount", "gap_amount", "rejected_amount"], 0)


def create_source_records(run_doc, amount):
    scope = latest_design_scope()
    if not scope:
        frappe.throw(_("No Phase 6A/6D design scope found."))
    company = scope.company
    receivable_account = scope.receivable_account
    if not company or not receivable_account:
        frappe.throw(_("Missing company or receivable account from approved design scope."))

    si_result = create_sales_invoice(run_doc.name, company, receivable_account, amount)
    sales_invoice = si_result["sales_invoice"]
    add_harness_line(run_doc.name, "Sales Invoice", "Sales Invoice", sales_invoice, "Controlled submitted Sales Invoice", "Submitted", amount, "Submitted controlled source invoice. This is intentional Phase 6E accounting source data.")

    claim_line = create_claim_line(run_doc.name, sales_invoice, company, amount)
    add_harness_line(run_doc.name, "Claim Line", "NDIS Claim Line", claim_line, "Controlled NDIS Claim Line", "Linked", amount, "Claim line linked to controlled source Sales Invoice.")

    remittance_import = create_remittance_import(run_doc.name, company, amount)
    add_harness_line(run_doc.name, "Remittance Import", "NDIS Remittance Import", remittance_import, "Controlled NDIS Remittance Import", "Created", amount, "Controlled remittance import created for Phase 6B preview eligibility.")

    remittance_line = create_remittance_line(run_doc.name, remittance_import, claim_line, sales_invoice, company, amount)
    add_harness_line(run_doc.name, "Remittance Import Line", "NDIS Remittance Import Line", remittance_line, "Controlled Paid Remittance Line", "Created", amount, "Paid remittance line linked to controlled claim line and Sales Invoice.")

    return {
        "company": company,
        "customer": si_result["customer"],
        "item": si_result["item"],
        "sales_invoice": sales_invoice,
        "claim_line": claim_line,
        "remittance_import": remittance_import,
        "remittance_line": remittance_line,
        "outstanding": si_result["outstanding"],
        "sales_invoice_gl_count": si_result["gl_count"],
        "sales_invoice_gl_net": si_result["gl_net"],
    }


@frappe.whitelist()
def run_real_remittance_pe_source_harness(amount=1, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_pe_source_harness")
    amount = flt(amount or 1)
    if amount <= 0:
        frappe.throw(_("Harness amount must be positive."))

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == HARNESS_ACK
    scope = latest_design_scope()
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "acknowledgement_ok": ack_ok,
        "required_acknowledgement": HARNESS_ACK,
        "source_amount": amount,
        "scope_found": bool(scope),
        "company": scope.company if scope else None,
        "real_posting_allowed": 0,
        "source_ready_for_preview": 0,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "note": "Phase 6E creates controlled eligible source data only. It does not create Payment Entry or Payment Entry GL.",
    }
    if int(dry_run or 0):
        result["status"] = "Previewed"
        return result

    run = frappe.new_doc(RUN_DOCTYPE)
    run.harness_run_id = make_harness_run_id()
    run.status = "Needs Review"
    run.harness_type = "Controlled Eligible Real Remittance Source"
    run.source_ready_for_preview = 0
    run.real_posting_allowed = 0
    run.source_amount = amount
    run.expected_phase6b_eligible_lines = 1
    run.expected_phase6c_would_create_pe = 1
    run.expected_phase6d_ready_for_smoke = 1
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = config["sandbox_enabled"]
    run.production_mode_detected = config["production_mode"]
    run.live_payment_entry_posting_config = config["live_pe_enabled"]
    run.checked_on = now_datetime()
    run.checked_by = frappe.session.user
    run.payment_entry_count_before = guard_before["payment_entry_count"]
    run.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    run.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run.live_enabled_policy_count = guard_before["live_enabled_policy_count"]
    run.required_acknowledgement = HARNESS_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(ack_ok)
    run.notes = notes

    if not ack_ok:
        run.summary_json = safe_json(result)
        run.insert(ignore_permissions=True)
        guard_after = guardrails()
        run.payment_entry_count_after = guard_after["payment_entry_count"]
        run.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]
        run.save(ignore_permissions=True)
        frappe.db.commit()
        result.update({
            "created": True,
            "harness_run": run.name,
            "harness_run_id": run.harness_run_id,
            "status": run.status,
            "source_ready_for_preview": 0,
            "real_posting_allowed": 0,
            "guardrails_after": guard_after,
        })
        return result

    if config["production_mode"] or config["live_pe_enabled"]:
        frappe.throw(_("Unsafe config: production mode or live PE posting config is enabled."))
    if guard_before["live_enabled_policy_count"]:
        frappe.throw(_("Live-enabled PE policy exists. Refusing to create source harness."))

    run.insert(ignore_permissions=True)
    source = create_source_records(run, amount)
    guard_after = guardrails()
    run.status = "Source Ready"
    run.source_ready_for_preview = 1
    run.real_posting_allowed = 0
    run.company = source["company"]
    run.customer = source["customer"]
    run.item = source["item"]
    run.sales_invoice = source["sales_invoice"]
    run.claim_line = source["claim_line"]
    run.remittance_import = source["remittance_import"]
    run.remittance_line = source["remittance_line"]
    run.invoice_outstanding_before_payment = source["outstanding"]
    run.sales_invoice_gl_count = source["sales_invoice_gl_count"]
    run.sales_invoice_gl_net = source["sales_invoice_gl_net"]
    run.payment_entry_count_after = guard_after["payment_entry_count"]
    run.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]

    result.update({
        "created": True,
        "harness_run": run.name,
        "harness_run_id": run.harness_run_id,
        "status": run.status,
        "source_ready_for_preview": 1,
        "company": source["company"],
        "customer": source["customer"],
        "item": source["item"],
        "sales_invoice": source["sales_invoice"],
        "claim_line": source["claim_line"],
        "remittance_import": source["remittance_import"],
        "remittance_line": source["remittance_line"],
        "invoice_outstanding_before_payment": source["outstanding"],
        "sales_invoice_gl_count": source["sales_invoice_gl_count"],
        "sales_invoice_gl_net": source["sales_invoice_gl_net"],
        "guardrails_after": guard_after,
    })
    run.summary_json = safe_json(result)
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_source_harness_audit(harness_run, reason=None):
    assert_action("cancel_real_remittance_pe_source_harness_audit")
    if not frappe.db.exists(RUN_DOCTYPE, harness_run):
        frappe.throw(_("Harness run not found: {0}").format(harness_run))
    doc = frappe.get_doc(RUN_DOCTYPE, harness_run)
    if int(doc.source_ready_for_preview or 0) or doc.sales_invoice:
        frappe.throw(_("Cannot cancel a source-created harness run in Phase 6E. It must be handled by the later controlled rollback phase."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        harness_run,
        {
            "status": "Cancelled",
            "source_ready_for_preview": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6E no-source audit harness cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET status = 'Cancelled' WHERE harness_run = %(harness_run)s", {"harness_run": harness_run})
    frappe.db.commit()
    return {
        "harness_run": harness_run,
        "status": "Cancelled",
        "note": "Audit-only harness run cancelled. No source or accounting movement was changed.",
    }


@frappe.whitelist()
def quick_real_remittance_pe_source_harness_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "harness_run_id",
            "status",
            "source_ready_for_preview",
            "real_posting_allowed",
            "company",
            "sales_invoice",
            "claim_line",
            "remittance_import",
            "remittance_line",
            "source_amount",
            "invoice_outstanding_before_payment",
            "sales_invoice_gl_count",
            "sales_invoice_gl_net",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=["name", "harness_run", "record_type", "record_doctype", "record_name", "record_label", "status", "amount", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": HARNESS_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6E source harness summary only. No Payment Entry or PE GL is created.",
    }


def execute_harness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(r.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "harness_run", "label": _("Harness Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "harness_run_id", "label": _("Harness Run ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_ready_for_preview", "label": _("Source Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "claim_line", "label": _("Claim Line"), "fieldtype": "Link", "options": "NDIS Claim Line", "width": 170},
        {"fieldname": "remittance_import", "label": _("Remittance Import"), "fieldtype": "Link", "options": "NDIS Remittance Import", "width": 190},
        {"fieldname": "remittance_line", "label": _("Remittance Line"), "fieldtype": "Link", "options": "NDIS Remittance Import Line", "width": 190},
        {"fieldname": "source_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "sales_invoice_gl_count", "label": _("SI GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "sales_invoice_gl_net", "label": _("SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_count_after", "label": _("PE Count After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS harness_run,
            r.harness_run_id,
            r.status,
            r.source_ready_for_preview,
            r.real_posting_allowed,
            r.sales_invoice,
            r.claim_line,
            r.remittance_import,
            r.remittance_line,
            r.source_amount,
            r.sales_invoice_gl_count,
            r.sales_invoice_gl_net,
            r.payment_entry_count_after,
            r.payment_entry_gl_count_after,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{RUN_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.harness_run_id for row in data[:20]],
            "datasets": [
                {"name": "Source Ready", "values": [int(row.source_ready_for_preview or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Harness Runs"), "datatype": "Int"},
        {"value": sum(int(row.source_ready_for_preview or 0) for row in data), "indicator": "Green", "label": _("Source Ready"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("harness_run"):
        conditions.append("l.harness_run = %(harness_run)s")
        params["harness_run"] = filters.harness_run
    if filters.get("record_type"):
        conditions.append("l.record_type = %(record_type)s")
        params["record_type"] = filters.record_type
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "harness_run", "label": _("Harness Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "record_type", "label": _("Record Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "record_doctype", "label": _("Record DocType"), "fieldtype": "Data", "width": 170},
        {"fieldname": "record_name", "label": _("Record Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 500},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.harness_run,
            l.record_type,
            l.record_doctype,
            l.record_name,
            l.status,
            l.amount,
            l.detail,
            l.checked_on,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.record_type or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Records", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status in ["Created", "Submitted", "Linked"]]), "indicator": "Green", "label": _("Created/Linked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_readiness_report(filters=None):
    columns, data, message, chart, summary = execute_harness_report(filters)
    summary.append({"value": count_dt("Payment Entry"), "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": count_dt("GL Entry", {"voucher_type": "Payment Entry"}), "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
