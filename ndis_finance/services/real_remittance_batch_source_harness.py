import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SOURCE_ACK = "I_CONFIRM_PHASE7E_CREATE_CONTROLLED_BATCH_SOURCE_ONLY_NO_PAYMENT_ENTRY"
RUN_DOCTYPE = "NDIS Real Remittance Batch Source Harness Run"
LINE_DOCTYPE = "NDIS Real Remittance Batch Source Harness Line"

HARNESS_CUSTOMER = "NDIS Batch Smoke Customer - Phase 7E"
HARNESS_ITEM = "NDIS-BATCH-SMOKE-SERVICE-7E"


def make_source_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-SOURCE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt("NDIS Real Remittance Batch Posting Policy", {"batch_live_enabled": 1}),
        "production_live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Real Remittance Batch Activation Gate",
        filters={
            "status": "Activation Allowed",
            "activation_allowed_for_controlled_smoke": 1,
            "ready_for_batch_smoke": 1,
            "adapter_hard_block_verified": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "adapter_run",
            "batch_preview",
            "design_gate",
            "company",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def get_single_value(doctype, filters=None, fieldname="name", order_by="creation asc"):
    rows = frappe.get_all(doctype, filters=filters or {}, fields=[fieldname], order_by=order_by, limit=1)
    return rows[0][fieldname] if rows else None


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


def get_leaf_account(company, root_type=None, account_type=None, preferred=None):
    if preferred and frappe.db.exists("Account", preferred):
        return preferred
    filters = {"company": company, "is_group": 0, "disabled": 0}
    if root_type:
        filters["root_type"] = root_type
    if account_type:
        filters["account_type"] = account_type
    return get_single_value("Account", filters, order_by="name asc")


def get_income_account(company):
    company_doc = frappe.get_doc("Company", company)
    if getattr(company_doc, "default_income_account", None):
        return company_doc.default_income_account
    account = get_leaf_account(company, "Income", "Income Account") or get_leaf_account(company, "Income")
    if not account:
        frappe.throw(_("No leaf Income account found for company {0}.").format(company))
    return account


def get_receivable_account(company, preferred=None):
    if preferred and frappe.db.exists("Account", preferred):
        return preferred
    company_doc = frappe.get_doc("Company", company)
    for fieldname in ["default_receivable_account", "default_account"]:
        account = getattr(company_doc, fieldname, None)
        if account and frappe.db.exists("Account", account):
            return account
    account = get_leaf_account(company, "Asset", "Receivable") or get_leaf_account(company, "Asset")
    if not account:
        frappe.throw(_("No leaf receivable Asset account found for company {0}.").format(company))
    return account


def get_cost_center(company):
    company_doc = frappe.get_doc("Company", company)
    if getattr(company_doc, "cost_center", None) and frappe.db.exists("Cost Center", company_doc.cost_center):
        return company_doc.cost_center
    cost_center = get_single_value("Cost Center", {"company": company, "is_group": 0, "disabled": 0}, order_by="name asc")
    if not cost_center:
        frappe.throw(_("No leaf Cost Center found for company {0}.").format(company))
    return cost_center


def ensure_customer():
    if frappe.db.exists("Customer", HARNESS_CUSTOMER):
        return HARNESS_CUSTOMER
    doc = frappe.new_doc("Customer")
    doc.customer_name = HARNESS_CUSTOMER
    doc.customer_type = "Company"
    if doc.meta.has_field("customer_group"):
        doc.customer_group = get_single_value("Customer Group", {"is_group": 0}) or "All Customer Groups"
    if doc.meta.has_field("territory"):
        doc.territory = get_single_value("Territory", {"is_group": 0}) or "All Territories"
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc.name


def ensure_item():
    if frappe.db.exists("Item", HARNESS_ITEM):
        return HARNESS_ITEM
    doc = frappe.new_doc("Item")
    doc.item_code = HARNESS_ITEM
    doc.item_name = "NDIS Batch Smoke Service Phase 7E"
    doc.item_group = get_single_value("Item Group", {"is_group": 0}) or "Services"
    doc.stock_uom = get_single_value("UOM", {"enabled": 1}) or "Nos"
    doc.is_stock_item = 0
    doc.is_sales_item = 1
    doc.is_purchase_item = 0
    doc.description = "Controlled Phase 7E batch smoke source harness item."
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc.name


def build_plan(activation):
    max_lines = int(activation.max_batch_lines or 0)
    max_amount = flt(activation.max_batch_amount or 0)
    planned_line_count = 2 if max_lines >= 2 and max_amount >= 2 else 1
    amount_each = 1
    planned_amount = planned_line_count * amount_each
    if planned_line_count > max_lines or planned_amount > max_amount:
        frappe.throw(_("Planned Phase 7E source exceeds Phase 7D activation caps."))
    return [
        {"line_no": idx, "amount": amount_each, "outcome": "Paid" if idx == 1 else "Short Paid"}
        for idx in range(1, planned_line_count + 1)
    ], planned_line_count, planned_amount


def create_sales_invoice(company, customer, item_code, amount, run_name, line_no, receivable_account=None):
    income_account = get_income_account(company)
    cost_center = get_cost_center(company)
    debit_to = get_receivable_account(company, receivable_account)
    si = frappe.new_doc("Sales Invoice")
    si.company = company
    si.customer = customer
    si.posting_date = today()
    si.due_date = add_days(today(), 7)
    si.currency = currency()
    si.debit_to = debit_to
    set_if_field(si, "custom_ndis_real_remittance_batch_source_invoice", 1)
    set_if_field(si, "custom_ndis_real_remittance_batch_source_run", run_name)
    set_if_field(si, "custom_ndis_real_remittance_batch_source_line_no", line_no)
    set_if_field(si, "custom_ndis_real_remittance_batch_source_amount", amount)
    si.remarks = "Controlled Phase 7E batch smoke source invoice. Do not use for live operations."
    si.append(
        "items",
        {
            "item_code": item_code,
            "qty": 1,
            "rate": flt(amount),
            "income_account": income_account,
            "cost_center": cost_center,
            "description": "Controlled Phase 7E batch smoke source item",
        },
    )
    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()
    return si.name


def create_claim_line(sales_invoice, amount, run_name, line_no, company):
    doc = frappe.new_doc("NDIS Claim Line")
    set_if_field(doc, "custom_ndis_real_remittance_batch_source", 1)
    set_if_field(doc, "custom_ndis_real_remittance_batch_source_run", run_name)
    set_if_field(doc, "custom_ndis_batch_source_sales_invoice", sales_invoice)
    set_if_field(doc, "custom_ndis_batch_source_amount", amount)
    set_first_field(doc, ["sales_invoice", "invoice", "sales_invoice_reference", "source_sales_invoice"], sales_invoice)
    set_first_field(doc, ["sales_invoice_item", "invoice_item", "sales_invoice_detail"], get_single_value("Sales Invoice Item", {"parent": sales_invoice}, fieldname="name"))
    set_first_field(doc, ["company"], company)
    set_first_field(doc, ["claim_amount", "amount", "claimed_amount", "line_amount"], flt(amount))
    set_first_field(doc, ["paid_amount", "received_amount", "settled_amount"], 0)
    set_first_field(doc, ["claim_status", "status", "invoice_status"], "Submitted")
    set_first_field(doc, ["claim_outcome", "outcome", "payment_outcome"], "Pending")
    set_if_field(doc, "line_no", line_no)
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def create_remittance_import(run_id, company):
    doc = frappe.new_doc("NDIS Remittance Import")
    set_first_field(doc, ["import_id", "remittance_import_id", "reference", "title"], run_id)
    set_first_field(doc, ["company"], company)
    set_first_field(doc, ["status", "import_status"], "Imported")
    set_first_field(doc, ["posting_date", "received_date", "import_date", "payment_date"], today())
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def populate_remittance_line(doc, remittance_import, sales_invoice, claim_line, amount, outcome, run_name, line_no, company):
    set_if_field(doc, "custom_ndis_real_remittance_batch_source", 1)
    set_if_field(doc, "custom_ndis_real_remittance_batch_source_run", run_name)
    set_if_field(doc, "custom_ndis_batch_source_sales_invoice", sales_invoice)
    set_if_field(doc, "custom_ndis_batch_source_claim_line", claim_line)
    set_if_field(doc, "custom_ndis_batch_source_outcome", outcome)
    set_if_field(doc, "custom_ndis_batch_source_amount", amount)
    set_first_field(doc, ["remittance_import", "ndis_remittance_import", "import_reference"], remittance_import)
    set_first_field(doc, ["sales_invoice", "invoice", "invoice_reference", "sales_invoice_reference", "erpnext_sales_invoice"], sales_invoice)
    set_first_field(doc, ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"], claim_line)
    set_first_field(doc, ["claim_outcome", "outcome", "payment_outcome", "invoice_status", "status"], outcome)
    set_first_field(doc, ["match_status", "matching_status"], "Matched")
    set_first_field(doc, ["paid_amount", "payment_amount", "received_amount", "allocated_amount", "amount"], flt(amount))
    set_first_field(doc, ["shortfall_amount", "variance_amount", "gap_amount", "rejected_amount"], 0)
    set_first_field(doc, ["company"], company)
    set_if_field(doc, "line_no", line_no)


def create_remittance_line(remittance_import, sales_invoice, claim_line, amount, outcome, run_name, line_no, company):
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
        populate_remittance_line(row, remittance_import, sales_invoice, claim_line, amount, outcome, run_name, line_no, company)
        parent.flags.ignore_mandatory = True
        parent.flags.ignore_links = True
        parent.save(ignore_permissions=True)
        return row.name
    doc = frappe.new_doc("NDIS Remittance Import Line")
    populate_remittance_line(doc, remittance_import, sales_invoice, claim_line, amount, outcome, run_name, line_no, company)
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
    return doc.name


def create_harness_line(run_name, line_no, sales_invoice, claim_line, remittance_import, remittance_line, amount, outcome):
    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.source_run = run_name
    doc.line_no = line_no
    doc.line_label = f"Phase 7E Line {line_no} - {outcome}"
    doc.line_status = "Ready"
    doc.sales_invoice = sales_invoice
    doc.claim_line = claim_line
    doc.remittance_import = remittance_import
    doc.remittance_line = remittance_line
    doc.expected_outcome = outcome
    doc.match_status = "Matched"
    doc.would_be_eligible_for_batch = 1
    doc.duplicate_invoice = 0
    doc.overpayment = 0
    doc.cross_company = 0
    doc.invoice_amount = flt(amount)
    doc.invoice_outstanding = flt(amount)
    doc.source_amount = flt(amount)
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


def controlled_si_gl_count_and_net(run_name):
    invoices = frappe.get_all("Sales Invoice", filters={"custom_ndis_real_remittance_batch_source_run": run_name}, pluck="name")
    if not invoices:
        return 0, 0
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type = 'Sales Invoice'
        AND voucher_no IN %(invoices)s
        """,
        {"invoices": tuple(invoices)},
        as_dict=True,
    )
    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append({"status": status, "severity": severity, "category": category, "check_key": check_key, "check_label": check_label, "detail": detail})


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


@frappe.whitelist()
def run_real_remittance_batch_source_harness(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_source_harness")
    activation = latest_activation_gate()
    if not activation:
        frappe.throw(_("No Phase 7D activation gate ready for controlled batch smoke."))

    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == SOURCE_ACK
    plan_lines, planned_line_count, planned_amount = build_plan(activation)

    items = []
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled." if config["live_pe_enabled"] else "Live PE posting remains disabled.")
    if guard_before["batch_live_enabled_policy_count"] == 0 and guard_before["production_live_enabled_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "live_policies", "Live policies", "No live-enabled batch or production PE policies.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "live_policies", "Live policies", "Live-enabled policy exists.")
    if planned_line_count <= int(activation.max_batch_lines or 0) and flt(planned_amount) <= flt(activation.max_batch_amount or 0):
        add_item(items, "Pass", "Low", "Batch Cap", "planned_source", "Planned source", f"Planned {planned_line_count} line(s), amount {planned_amount}.")
    else:
        add_item(items, "Blocker", "Critical", "Batch Cap", "planned_source", "Planned source", "Planned source exceeds activation cap.")
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "source_ack", "Source acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "source_ack", "Source acknowledgement", f"Required acknowledgement not supplied: {SOURCE_ACK}")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    source_allowed = int(ack_ok and item_summary["blocker_count"] == 0)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Source Created" if source_allowed else "Needs Review",
        "source_status": "Ready For Controlled Batch Smoke" if source_allowed else "Audit Only",
        "source_created_for_batch_smoke": source_allowed,
        "ready_for_batch_smoke": source_allowed,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "activation_gate": activation.name,
        "adapter_run": activation.adapter_run,
        "batch_preview": activation.batch_preview,
        "design_gate": activation.design_gate,
        "company": activation.company,
        "max_batch_lines": int(activation.max_batch_lines or 0),
        "max_batch_amount": flt(activation.max_batch_amount or 0),
        "planned_source_line_count": planned_line_count,
        "planned_source_amount": flt(planned_amount, 2),
        "created_sales_invoice_count": 0,
        "submitted_sales_invoice_count": 0,
        "created_claim_line_count": 0,
        "created_remittance_line_count": 0,
        "eligible_source_line_count": 0,
        "source_amount": 0,
        "controlled_sales_invoice_gl_count": 0,
        "controlled_sales_invoice_gl_net": 0,
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_gl_created_count": 0,
        "source_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": SOURCE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7E creates controlled source records only. No Payment Entry or Payment Entry GL is created.",
    }
    if int(dry_run or 0):
        return result

    run = frappe.new_doc(RUN_DOCTYPE)
    run.source_run_id = make_source_run_id()
    for fieldname, value in result.items():
        if run.meta.has_field(fieldname):
            setattr(run, fieldname, value)
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = config["sandbox_enabled"]
    run.production_mode_detected = config["production_mode"]
    run.live_payment_entry_posting_config = config["live_pe_enabled"]
    run.checked_on = now_datetime()
    run.checked_by = frappe.session.user
    run.payment_entry_count_before = guard_before["payment_entry_count"]
    run.payment_entry_count_after = guardrails()["payment_entry_count"]
    run.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    run.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    run.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run.batch_live_enabled_policy_count = guard_before["batch_live_enabled_policy_count"]
    run.production_live_enabled_policy_count = guard_before["production_live_enabled_policy_count"]
    run.required_acknowledgement = SOURCE_ACK
    run.acknowledgement = acknowledgement
    run.acknowledgement_ok = int(ack_ok)
    run.summary_json = safe_json(result)
    run.notes = notes
    run.insert(ignore_permissions=True)

    customer = None
    item_code = None
    remittance_import = None
    counters = {
        "created_sales_invoice_count": 0,
        "submitted_sales_invoice_count": 0,
        "created_claim_line_count": 0,
        "created_remittance_line_count": 0,
        "eligible_source_line_count": 0,
        "source_amount": 0,
    }

    if source_allowed:
        customer = ensure_customer()
        item_code = ensure_item()
        remittance_import = create_remittance_import(run.source_run_id, activation.company)
        for planned in plan_lines:
            line_no = planned["line_no"]
            amount = flt(planned["amount"])
            outcome = planned["outcome"]
            sales_invoice = create_sales_invoice(activation.company, customer, item_code, amount, run.name, line_no, activation.receivable_account)
            claim_line = create_claim_line(sales_invoice, amount, run.name, line_no, activation.company)
            remittance_line = create_remittance_line(remittance_import, sales_invoice, claim_line, amount, outcome, run.name, line_no, activation.company)
            create_harness_line(run.name, line_no, sales_invoice, claim_line, remittance_import, remittance_line, amount, outcome)
            counters["created_sales_invoice_count"] += 1
            counters["submitted_sales_invoice_count"] += 1
            counters["created_claim_line_count"] += 1
            counters["created_remittance_line_count"] += 1
            counters["eligible_source_line_count"] += 1
            counters["source_amount"] += amount

    controlled_gl_count, controlled_gl_net = controlled_si_gl_count_and_net(run.name)
    guard_after = guardrails()
    updates = {
        **counters,
        "source_amount": flt(counters["source_amount"], 2),
        "customer": customer,
        "item": item_code,
        "source_remittance_import": remittance_import,
        "controlled_sales_invoice_gl_count": controlled_gl_count,
        "controlled_sales_invoice_gl_net": controlled_gl_net,
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_gl_created_count": 0,
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
    }
    result.update(updates)
    result["created"] = True
    result["source_run"] = run.name
    result["source_run_id"] = run.source_run_id
    result["guardrails_after"] = guard_after
    updates["summary_json"] = safe_json(result)
    frappe.db.set_value(RUN_DOCTYPE, run.name, updates, update_modified=False)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_source_harness(source_run, reason=None):
    assert_action("cancel_real_remittance_batch_source_harness")
    if not frappe.db.exists(RUN_DOCTYPE, source_run):
        frappe.throw(_("Source harness run not found: {0}").format(source_run))
    doc = frappe.get_doc(RUN_DOCTYPE, source_run)
    if doc.status == "Cancelled":
        return {"source_run": source_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.ready_for_batch_smoke or 0):
        frappe.throw(_("Cannot cancel a ready controlled source harness. It is required for the next smoke phase."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        source_run,
        {
            "status": "Cancelled",
            "source_status": "Cancelled",
            "source_created_for_batch_smoke": 0,
            "ready_for_batch_smoke": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7E source harness audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE source_run = %(source_run)s", {"source_run": source_run})
    frappe.db.commit()
    return {"source_run": source_run, "status": "Cancelled", "note": "Source harness audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_source_harness_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "source_run_id",
            "status",
            "source_status",
            "source_created_for_batch_smoke",
            "ready_for_batch_smoke",
            "batch_posting_allowed",
            "real_posting_allowed",
            "activation_gate",
            "company",
            "customer",
            "item",
            "source_remittance_import",
            "created_sales_invoice_count",
            "submitted_sales_invoice_count",
            "created_claim_line_count",
            "created_remittance_line_count",
            "eligible_source_line_count",
            "source_amount",
            "controlled_sales_invoice_gl_count",
            "controlled_sales_invoice_gl_net",
            "actual_payment_entry_created_count",
            "actual_payment_entry_gl_created_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=["name", "source_run", "line_no", "line_status", "sales_invoice", "claim_line", "remittance_line", "expected_outcome", "source_amount", "would_be_eligible_for_batch"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": SOURCE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 7E source harness summary. Controlled source records only; no Payment Entry or PE GL is created.",
    }


def harness_columns():
    return [
        {"fieldname": "source_run", "label": _("Source Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "source_run_id", "label": _("Source Run ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_status", "label": _("Source Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "ready_for_batch_smoke", "label": _("Ready Smoke"), "fieldtype": "Check", "width": 110},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "eligible_source_line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 110},
        {"fieldname": "source_amount", "label": _("Source Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "controlled_sales_invoice_gl_count", "label": _("SI GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "controlled_sales_invoice_gl_net", "label": _("SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_payment_entry_gl_created_count", "label": _("Actual PE GL"), "fieldtype": "Int", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_harness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("from_date"):
        conditions.append("DATE(r.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(r.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS source_run,
            r.source_run_id,
            r.status,
            r.source_status,
            r.ready_for_batch_smoke,
            r.batch_posting_allowed,
            r.real_posting_allowed,
            r.eligible_source_line_count,
            r.source_amount,
            r.controlled_sales_invoice_gl_count,
            r.controlled_sales_invoice_gl_net,
            r.actual_payment_entry_created_count,
            r.actual_payment_entry_gl_created_count,
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
            "labels": [row.source_run_id for row in data[:20]],
            "datasets": [
                {"name": "Source Lines", "values": [int(row.eligible_source_line_count or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "PE GL", "values": [int(row.actual_payment_entry_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Source Runs"), "datatype": "Int"},
        {"value": sum(int(row.eligible_source_line_count or 0) for row in data), "indicator": "Green", "label": _("Eligible Source Lines"), "datatype": "Int"},
        {"value": sum(flt(row.source_amount or 0) for row in data), "indicator": "Blue", "label": _("Source Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PEs"), "datatype": "Int"},
    ]
    return harness_columns(), data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("source_run"):
        conditions.append("l.source_run = %(source_run)s")
        params["source_run"] = filters.get("source_run")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "source_run", "label": _("Source Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "claim_line", "label": _("Claim Line"), "fieldtype": "Link", "options": "NDIS Claim Line", "width": 160},
        {"fieldname": "remittance_line", "label": _("Remittance Line"), "fieldtype": "Link", "options": "NDIS Remittance Import Line", "width": 200},
        {"fieldname": "expected_outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 120},
        {"fieldname": "would_be_eligible_for_batch", "label": _("Eligible"), "fieldtype": "Check", "width": 90},
        {"fieldname": "source_amount", "label": _("Source Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.source_run,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.claim_line,
            l.remittance_line,
            l.expected_outcome,
            l.would_be_eligible_for_batch,
            l.source_amount,
            l.checked_on,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.source_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [str(row.line_no) for row in data[:20]], "datasets": [{"name": "Amount", "values": [flt(row.source_amount or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(int(row.would_be_eligible_for_batch or 0) for row in data), "indicator": "Green", "label": _("Eligible"), "datatype": "Int"},
        {"value": sum(flt(row.source_amount or 0) for row in data), "indicator": "Blue", "label": _("Amount"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_harness_report(filters)
    summary.extend(
        [
            {"value": count_dt("Payment Entry"), "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": count_dt("GL Entry", {"voucher_type": "Payment Entry"}), "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}), "indicator": "Red", "label": _("Submitted JEs Today"), "datatype": "Int"},
            {"value": count_dt("Purchase Invoice", {"creation": [">=", today()]}), "indicator": "Red", "label": _("Purchase Invoices Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
