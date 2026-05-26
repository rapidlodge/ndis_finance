import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SOURCE_ACK = "I_CONFIRM_CREATE_PHASE5H_SUBMITTED_SI_SOURCE_NO_PE"
SOURCE_CANCEL_ACK = "I_CONFIRM_CANCEL_PHASE5H_SOURCE_INVOICE_ONLY"
CUSTOMER_NAME = "NDIS PE Smoke Test Customer"
ITEM_CODE = "NDIS-PE-SMOKE-SOURCE-ITEM"


def make_source_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-SMOKE-SI-SOURCE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=fields or ["name"],
        order_by=order_by,
        limit=1,
    )
    return rows[0] if rows else None


def add_item(items, status, severity, category, check_key, check_label, detail, recommendation=None, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "recommendation": recommendation,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def payment_guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }


def sales_invoice_gl_count(sales_invoice):
    return count_dt("GL Entry", {"voucher_type": "Sales Invoice", "voucher_no": sales_invoice}) if sales_invoice else 0


def sales_invoice_gl_net(sales_invoice):
    if not sales_invoice or not frappe.db.exists("DocType", "GL Entry"):
        return 0
    value = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
        FROM `tabGL Entry`
        WHERE voucher_type = 'Sales Invoice'
        AND voucher_no = %(sales_invoice)s
        """,
        {"sales_invoice": sales_invoice},
    )[0][0]
    return flt(value, 2)


def latest_activation_gate():
    return latest_doc(
        "NDIS PE Production Activation Gate",
        {
            "production_activation_allowed": 1,
            "ready_for_single_record_live_smoke": 1,
            "live_posting_allowed": 0,
            "payment_entry_created": 0,
            "blocker_count": 0,
        },
        ["name", "activation_gate_id", "company", "allowed_bank_account", "allowed_receivable_account"],
        "checked_on desc, creation desc",
    )


def latest_submitted_smoke_gate():
    return latest_doc(
        "NDIS PE Submitted Smoke Gate",
        {"source_pending": 1, "live_posting_allowed": 0, "payment_entry_created": 0, "payment_entry_submitted": 0},
        ["name", "submitted_smoke_gate_id", "status", "gate_status"],
        "checked_on desc, creation desc",
    )


def account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        return None
    return frappe.get_doc("Account", account)


def evaluate_config(items):
    config = config_state()
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Keep disabled for Phase 5H.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")
    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.", "Keep disabled for Phase 5H.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting remains disabled.")
    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")
    return config


def evaluate_evidence(items):
    activation = latest_activation_gate()
    submitted_gate = latest_submitted_smoke_gate()
    if activation:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5e_activation", "Phase 5E activation gate", f"Activation gate found: {activation.activation_gate_id}.", None, "NDIS PE Production Activation Gate", activation.name)
    else:
        add_item(items, "Blocker", "Critical", "Prior Evidence", "phase5e_activation", "Phase 5E activation gate", "No valid Phase 5E activation gate found.", "Complete Phase 5E before Phase 5H.")
    if submitted_gate:
        add_item(items, "Pass", "Low", "Prior Evidence", "phase5g_source_pending", "Phase 5G source-pending gate", f"Source-pending gate found: {submitted_gate.submitted_smoke_gate_id}.", None, "NDIS PE Submitted Smoke Gate", submitted_gate.name)
    else:
        add_item(items, "Warning", "Medium", "Prior Evidence", "phase5g_source_pending", "Phase 5G source-pending gate", "No source-pending Phase 5G gate found.", "Phase 5H can still create a source invoice if Phase 5E is ready.")
    return activation, submitted_gate


def find_income_account(company):
    for filters in (
        {"company": company, "root_type": "Income", "account_type": "Income Account", "is_group": 0, "disabled": 0},
        {"company": company, "root_type": "Income", "is_group": 0, "disabled": 0},
    ):
        row = frappe.get_all("Account", filters=filters, fields=["name"], order_by="name asc", limit=1)
        if row:
            return row[0].name
    return None


def find_cost_center(company):
    company_doc = frappe.get_doc("Company", company)
    if getattr(company_doc, "cost_center", None) and frappe.db.exists("Cost Center", company_doc.cost_center):
        return company_doc.cost_center
    row = frappe.get_all(
        "Cost Center",
        filters={"company": company, "is_group": 0, "disabled": 0},
        fields=["name"],
        order_by="name asc",
        limit=1,
    )
    return row[0].name if row else None


def first_value(doctype, filters, fallback=None):
    row = frappe.get_all(doctype, filters=filters, fields=["name"], order_by="name asc", limit=1)
    if row:
        return row[0].name
    if fallback and frappe.db.exists(doctype, fallback):
        return fallback
    return None


def evaluate_accounts_and_master_data(items, activation):
    result = {}
    if not activation:
        return result
    company = activation.company
    receivable = account_doc(activation.allowed_receivable_account)
    bank = account_doc(activation.allowed_bank_account)
    result.update(
        {
            "company": company,
            "allowed_receivable_account": activation.allowed_receivable_account,
            "allowed_bank_account": activation.allowed_bank_account,
            "income_account": find_income_account(company),
            "cost_center": find_cost_center(company),
            "customer_group": first_value("Customer Group", {"is_group": 0}, "All Customer Groups"),
            "territory": first_value("Territory", {"is_group": 0}, "All Territories"),
            "item_group": first_value("Item Group", {"is_group": 0}, "All Item Groups"),
        }
    )
    if not company or not frappe.db.exists("Company", company):
        add_item(items, "Blocker", "Critical", "Account Control", "company", "Company", "Company is missing or invalid.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "company", "Company", f"Company verified: {company}.")
    if not receivable:
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Receivable account", "Receivable account is missing.")
    elif receivable.company != company or receivable.root_type != "Asset" or int(receivable.is_group or 0) or int(receivable.disabled or 0):
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Receivable account", "Receivable account is invalid.")
    elif receivable.account_type and receivable.account_type != "Receivable":
        add_item(items, "Blocker", "Critical", "Account Control", "receivable", "Receivable account", f"Receivable account type is {receivable.account_type}; expected Receivable.")
    else:
        add_item(items, "Pass", "Low", "Account Control", "receivable", "Receivable account", f"Receivable account verified: {activation.allowed_receivable_account}.", None, "Account", activation.allowed_receivable_account)
    if bank:
        add_item(items, "Pass", "Low", "Account Control", "bank", "Bank account", f"Bank account available for later PE smoke: {activation.allowed_bank_account}.", None, "Account", activation.allowed_bank_account)
    else:
        add_item(items, "Warning", "Medium", "Account Control", "bank", "Bank account", "Bank account not found. This invoice source phase does not create Payment Entry.")
    for key, label, category in [
        ("income_account", "Income account", "Account Control"),
        ("cost_center", "Cost Center", "Account Control"),
        ("customer_group", "Customer Group", "Master Data"),
        ("territory", "Territory", "Master Data"),
        ("item_group", "Item Group", "Master Data"),
    ]:
        if result.get(key):
            add_item(items, "Pass", "Low", category, key, label, f"{label} selected: {result[key]}.")
        else:
            add_item(items, "Blocker", "Critical", category, key, label, f"No {label} found.")
    return result


def existing_active_source_invoice():
    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "custom_ndis_pe_smoke_source_invoice": 1,
            "docstatus": 1,
            "outstanding_amount": [">", 0],
        },
        fields=["name", "outstanding_amount", "company"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def evaluate_existing_source(items):
    existing = existing_active_source_invoice()
    if existing:
        add_item(items, "Blocker", "Critical", "Duplicate Source", "existing_active_source_invoice", "Existing active smoke source invoice", f"Existing active Phase 5H source invoice found: {existing.name}.", "Use the existing invoice or cancel it after downstream tests before creating another.", "Sales Invoice", existing.name)
    else:
        add_item(items, "Pass", "Low", "Duplicate Source", "existing_active_source_invoice", "Existing active smoke source invoice", "No active Phase 5H source invoice exists.")
    return existing


def evaluate_policy_controls(items):
    checks = {
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
        "cross_company_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_cross_company_posting": 1}),
        "overpayment_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_overpayment": 1}),
        "negative_receipt_allowed_count": count_dt("NDIS PE Production Posting Policy", {"allow_negative_receipt": 1}),
    }
    labels = {
        "live_enabled_policy_count": "Live-enabled policies",
        "cross_company_allowed_count": "Cross-company allowed policies",
        "overpayment_allowed_count": "Overpayment allowed policies",
        "negative_receipt_allowed_count": "Negative receipt allowed policies",
    }
    for key, value in checks.items():
        if value:
            add_item(items, "Blocker", "Critical", "Policy Control", key, labels[key], f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Policy Control", key, labels[key], "Zero.")
    return checks


def evaluate_payment_guardrails(items):
    values = payment_guardrails()
    checks = [
        ("submitted_payment_entry_count_today", "Submitted Payment Entries today", values["submitted_payment_entry_count_today"]),
        ("payment_entry_gl_count", "Payment Entry GL", values["payment_entry_gl_count"]),
        ("payment_entry_gl_count_today", "Payment Entry GL today", values["payment_entry_gl_count_today"]),
        ("submitted_journal_entry_count_today", "Submitted Journal Entries today", values["submitted_journal_entry_count_today"]),
        ("purchase_invoice_count_today", "Purchase Invoices today", values["purchase_invoice_count_today"]),
    ]
    for key, label, value in checks:
        if value:
            add_item(items, "Blocker", "Critical", "Payment Guardrail", key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Payment Guardrail", key, label, "Zero.")
    return values


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


def source_status(score, blockers, warnings, source_created):
    if blockers:
        return "Blocked"
    if source_created:
        return "Source Invoice Created"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready To Create Source Invoice"
    return "Needs Review"


def ensure_customer(customer_group, territory):
    existing = frappe.db.exists("Customer", CUSTOMER_NAME)
    if existing:
        return frappe.get_doc("Customer", existing)
    doc = frappe.new_doc("Customer")
    doc.customer_name = CUSTOMER_NAME
    doc.customer_type = "Individual"
    doc.customer_group = customer_group
    doc.territory = territory
    doc.insert(ignore_permissions=True)
    return doc


def ensure_item(item_group):
    existing = frappe.db.exists("Item", ITEM_CODE)
    if existing:
        return frappe.get_doc("Item", existing)
    doc = frappe.new_doc("Item")
    doc.item_code = ITEM_CODE
    doc.item_name = "NDIS PE Smoke Source Item"
    doc.item_group = item_group
    doc.stock_uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
    doc.is_stock_item = 0
    doc.is_sales_item = 1
    doc.disabled = 0
    doc.description = "Controlled Phase 5H Payment Entry smoke-test invoice source item."
    doc.insert(ignore_permissions=True)
    return doc


def create_source_invoice(run_doc, customer, item, controls, amount):
    si = frappe.new_doc("Sales Invoice")
    si.company = controls["company"]
    si.customer = customer.name
    si.posting_date = today()
    si.due_date = today()
    si.debit_to = controls["allowed_receivable_account"]
    si.remarks = f"Controlled Phase 5H Sales Invoice source for future single-record Payment Entry smoke. Run: {run_doc.name}"
    si.custom_ndis_pe_smoke_source_invoice = 1
    si.custom_ndis_pe_smoke_source_run = run_doc.name
    si.custom_ndis_pe_smoke_source_phase = "Phase 5H"
    si.custom_ndis_pe_smoke_source_note = "Controlled submitted Sales Invoice source only. No Payment Entry created by Phase 5H."
    si.custom_ndis_pe_smoke_source_cancelled = 0
    si.append(
        "items",
        {
            "item_code": item.name,
            "item_name": item.item_name,
            "description": "Controlled Phase 5H Payment Entry smoke-test invoice source",
            "qty": 1,
            "rate": amount,
            "income_account": controls["income_account"],
            "cost_center": controls["cost_center"],
        },
    )
    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()
    return si


def create_run_items(run_doc, items):
    for item in items:
        row = frappe.new_doc("NDIS PE Smoke Invoice Source Run Item")
        row.source_run = run_doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = run_doc.executed_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_pe_smoke_invoice_source_harness(amount=1, acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_smoke_invoice_source_harness")
    amount = flt(amount or 1)
    items = []
    config = evaluate_config(items)
    activation, submitted_gate = evaluate_evidence(items)
    controls = evaluate_accounts_and_master_data(items, activation)
    existing_source = evaluate_existing_source(items)
    policy_controls = evaluate_policy_controls(items)
    guard_before = evaluate_payment_guardrails(items)
    if amount <= 0:
        add_item(items, "Blocker", "Critical", "Amount", "source_amount", "Source amount", "Source amount must be positive.")
    elif amount > 1:
        add_item(items, "Warning", "Medium", "Amount", "source_amount", "Source amount", f"Source amount is {amount}. Recommended smoke amount is 1.00.")
    else:
        add_item(items, "Pass", "Low", "Amount", "source_amount", "Source amount", f"Source amount set to {amount:.2f}.")
    ack_ok = acknowledgement == SOURCE_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "source_ack", "Source creation acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "source_ack", "Source creation acknowledgement", f"Required acknowledgement not supplied. Required: {SOURCE_ACK}", "Provide exact acknowledgement before creating source invoice.")
    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    if int(dry_run or 0):
        return {
            "dry_run": True,
            "status": "Previewed" if summary["blocker_count"] == 0 else "Blocked",
            "source_status": source_status(score, summary["blocker_count"], summary["warning_count"], False),
            "source_score": score,
            "source_invoice_created": 0,
            "source_invoice_submitted": 0,
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
            "live_posting_allowed": 0,
            "required_acknowledgement": SOURCE_ACK,
            "acknowledgement_ok": ack_ok,
            "activation_gate": activation.name if activation else None,
            "submitted_smoke_gate": submitted_gate.name if submitted_gate else None,
            "controls": controls,
            "policy_controls": policy_controls,
            "existing_source": existing_source,
            "guardrails_before": guard_before,
            "summary": summary,
            "items": items,
            "note": "Dry-run only. No Sales Invoice or Payment Entry was created.",
        }
    run_doc = frappe.new_doc("NDIS PE Smoke Invoice Source Run")
    run_doc.source_run_id = make_source_run_id()
    run_doc.status = "Needs Review" if not ack_ok else ("Blocked" if summary["blocker_count"] else "Previewed")
    run_doc.run_type = "Controlled Submitted Sales Invoice Source"
    for fieldname in ["company", "allowed_receivable_account", "allowed_bank_account", "income_account", "cost_center"]:
        setattr(run_doc, fieldname, controls.get(fieldname))
    run_doc.source_amount = amount
    run_doc.activation_gate = activation.name if activation else None
    run_doc.submitted_smoke_gate = submitted_gate.name if submitted_gate else None
    run_doc.site_name = frappe.local.site
    run_doc.sandbox_config_enabled = config["sandbox_enabled"]
    run_doc.production_mode_detected = config["production_mode"]
    run_doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    run_doc.executed_on = now_datetime()
    run_doc.executed_by = frappe.session.user
    run_doc.source_score = score
    run_doc.source_status = source_status(score, summary["blocker_count"], summary["warning_count"], False)
    for fieldname, value in summary.items():
        setattr(run_doc, fieldname, value)
    run_doc.source_invoice_created = 0
    run_doc.source_invoice_submitted = 0
    run_doc.source_invoice_cancelled = 0
    run_doc.payment_entry_created = 0
    run_doc.payment_entry_submitted = 0
    run_doc.live_posting_allowed = 0
    run_doc.payment_entry_count_before = guard_before["payment_entry_count"]
    run_doc.payment_entry_count_after = count_dt("Payment Entry")
    run_doc.submitted_payment_entry_count_today = guard_before["submitted_payment_entry_count_today"]
    run_doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    run_doc.payment_entry_gl_count_today = guard_before["payment_entry_gl_count_today"]
    run_doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    run_doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    run_doc.required_acknowledgement = SOURCE_ACK
    run_doc.acknowledgement = acknowledgement
    run_doc.acknowledgement_ok = int(ack_ok)
    run_doc.notes = notes
    run_doc.insert(ignore_permissions=True)
    create_run_items(run_doc, items)
    created_si = created_customer = created_item = None
    if ack_ok and summary["blocker_count"] == 0:
        created_customer = ensure_customer(controls["customer_group"], controls["territory"])
        created_item = ensure_item(controls["item_group"])
        created_si = create_source_invoice(run_doc, created_customer, created_item, controls, amount)
        frappe.db.set_value(
            "NDIS PE Smoke Invoice Source Run",
            run_doc.name,
            {
                "status": "Source Created",
                "source_status": "Source Invoice Created",
                "source_sales_invoice": created_si.name,
                "source_customer": created_customer.name,
                "source_item": created_item.name,
                "invoice_docstatus": created_si.docstatus,
                "invoice_outstanding_amount": flt(created_si.outstanding_amount),
                "invoice_gl_count": sales_invoice_gl_count(created_si.name),
                "invoice_gl_net": sales_invoice_gl_net(created_si.name),
                "source_invoice_created": 1,
                "source_invoice_submitted": int(created_si.docstatus == 1),
            },
            update_modified=False,
        )
    guard_after = payment_guardrails()
    result = {
        "dry_run": False,
        "created": True,
        "source_run": run_doc.name,
        "source_run_id": run_doc.source_run_id,
        "status": frappe.db.get_value("NDIS PE Smoke Invoice Source Run", run_doc.name, "status"),
        "source_status": frappe.db.get_value("NDIS PE Smoke Invoice Source Run", run_doc.name, "source_status"),
        "source_score": score,
        "source_sales_invoice": created_si.name if created_si else None,
        "source_customer": created_customer.name if created_customer else None,
        "source_item": created_item.name if created_item else None,
        "source_amount": amount,
        "source_invoice_created": 1 if created_si else 0,
        "source_invoice_submitted": 1 if created_si and created_si.docstatus == 1 else 0,
        "invoice_outstanding_amount": flt(created_si.outstanding_amount) if created_si else 0,
        "invoice_gl_count": sales_invoice_gl_count(created_si.name) if created_si else 0,
        "invoice_gl_net": sales_invoice_gl_net(created_si.name) if created_si else 0,
        "payment_entry_created": 0,
        "payment_entry_submitted": 0,
        "live_posting_allowed": 0,
        "required_acknowledgement": SOURCE_ACK,
        "acknowledgement_ok": ack_ok,
        "activation_gate": activation.name if activation else None,
        "submitted_smoke_gate": submitted_gate.name if submitted_gate else None,
        "summary": summary,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "note": "Phase 5H creates a controlled submitted Sales Invoice source only. No Payment Entry or Payment Entry GL is created.",
    }
    frappe.db.set_value(
        "NDIS PE Smoke Invoice Source Run",
        run_doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "submitted_payment_entry_count_today": guard_after["submitted_payment_entry_count_today"],
            "payment_entry_gl_count": guard_after["payment_entry_gl_count"],
            "payment_entry_gl_count_today": guard_after["payment_entry_gl_count_today"],
            "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
            "summary_json": safe_json(result),
        },
        update_modified=False,
    )
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_pe_smoke_invoice_source(source_run, acknowledgement=None):
    assert_action("cancel_pe_smoke_invoice_source")
    if acknowledgement != SOURCE_CANCEL_ACK:
        frappe.throw(_("Wrong acknowledgement. Required: {0}").format(SOURCE_CANCEL_ACK))
    if not frappe.db.exists("NDIS PE Smoke Invoice Source Run", source_run):
        frappe.throw(_("Source run not found: {0}").format(source_run))
    run = frappe.get_doc("NDIS PE Smoke Invoice Source Run", source_run)
    if not run.source_sales_invoice:
        frappe.throw(_("No source Sales Invoice linked to source run."))
    si = frappe.get_doc("Sales Invoice", run.source_sales_invoice)
    if not int(getattr(si, "custom_ndis_pe_smoke_source_invoice", 0) or 0):
        frappe.throw(_("Sales Invoice is not tagged as Phase 5H PE smoke source."))
    linked_pe_refs = frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabPayment Entry Reference`
        WHERE reference_doctype = 'Sales Invoice'
        AND reference_name = %(sales_invoice)s
        """,
        {"sales_invoice": si.name},
    )[0][0]
    if linked_pe_refs:
        frappe.throw(_("Cannot cancel source invoice because Payment Entry Reference rows exist: {0}").format(linked_pe_refs))
    if si.docstatus == 1:
        si.cancel()
    frappe.db.set_value("Sales Invoice", si.name, {"custom_ndis_pe_smoke_source_cancelled": 1}, update_modified=False)
    frappe.db.set_value(
        "NDIS PE Smoke Invoice Source Run",
        source_run,
        {
            "status": "Source Cancelled",
            "source_invoice_cancelled": 1,
            "invoice_docstatus": frappe.db.get_value("Sales Invoice", si.name, "docstatus"),
            "invoice_outstanding_amount": flt(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount") or 0),
            "invoice_gl_count": sales_invoice_gl_count(si.name),
            "invoice_gl_net": sales_invoice_gl_net(si.name),
            "source_cancelled_on": now_datetime(),
            "source_cancelled_by": frappe.session.user,
            "payment_entry_count_after": count_dt("Payment Entry"),
            "submitted_payment_entry_count_today": count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
            "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
            "payment_entry_gl_count_today": count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}),
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "status": "Source Cancelled",
        "source_run": source_run,
        "sales_invoice": si.name,
        "invoice_docstatus": frappe.db.get_value("Sales Invoice", si.name, "docstatus"),
        "invoice_gl_count": sales_invoice_gl_count(si.name),
        "invoice_gl_net": sales_invoice_gl_net(si.name),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "note": "Source invoice cancelled only. This creates normal Sales Invoice reversal GL, not Payment Entry GL.",
    }


@frappe.whitelist()
def cancel_pe_smoke_invoice_source_run(source_run, reason=None):
    assert_action("cancel_pe_smoke_invoice_source_run")
    if not frappe.db.exists("NDIS PE Smoke Invoice Source Run", source_run):
        frappe.throw(_("Source run not found: {0}").format(source_run))
    run = frappe.get_doc("NDIS PE Smoke Invoice Source Run", source_run)
    if run.source_sales_invoice and frappe.db.exists("Sales Invoice", run.source_sales_invoice):
        si_docstatus = frappe.db.get_value("Sales Invoice", run.source_sales_invoice, "docstatus")
        if si_docstatus == 1:
            frappe.throw(_("Cancel the linked source Sales Invoice first, or keep the run active for downstream smoke tests: {0}").format(run.source_sales_invoice))
    frappe.db.set_value(
        "NDIS PE Smoke Invoice Source Run",
        source_run,
        {
            "status": "Cancelled",
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
            "live_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 5H source run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        "UPDATE `tabNDIS PE Smoke Invoice Source Run Item` SET status = 'Cancelled' WHERE source_run = %(source_run)s",
        {"source_run": source_run},
    )
    frappe.db.commit()
    return {"source_run": source_run, "status": "Cancelled", "note": "Source run cancelled. No Payment Entry movement occurred."}


@frappe.whitelist()
def quick_pe_smoke_invoice_source_summary(limit=20):
    runs = frappe.get_all(
        "NDIS PE Smoke Invoice Source Run",
        fields=[
            "name",
            "source_run_id",
            "status",
            "source_status",
            "source_score",
            "source_sales_invoice",
            "source_amount",
            "invoice_docstatus",
            "invoice_outstanding_amount",
            "invoice_gl_count",
            "invoice_gl_net",
            "source_invoice_created",
            "source_invoice_submitted",
            "source_invoice_cancelled",
            "payment_entry_created",
            "payment_entry_submitted",
            "payment_entry_gl_count",
            "executed_on",
            "executed_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS PE Smoke Invoice Source Run Item",
        fields=["name", "source_run", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "items": items,
        "required_acknowledgement": SOURCE_ACK,
        "source_cancel_acknowledgement": SOURCE_CANCEL_ACK,
        "payment_guardrails": payment_guardrails(),
        "config": config_state(),
        "note": "Phase 5H summary. Sales Invoice GL is expected for submitted source invoice. Payment Entry GL must remain zero.",
    }


def execute_source_run_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(r.executed_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(r.executed_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "source_run", "label": _("Source Run"), "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run", "width": 220},
        {"fieldname": "source_run_id", "label": _("Source Run ID"), "fieldtype": "Data", "width": 330},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "source_status", "label": _("Source Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_sales_invoice", "label": _("Source Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "source_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "invoice_outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_gl_count", "label": _("Invoice GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_created", "label": _("PE Created"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry_submitted", "label": _("PE Submitted"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 80},
        {"fieldname": "executed_on", "label": _("Executed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS source_run, r.source_run_id, r.status, r.source_status,
            r.source_sales_invoice, r.source_amount, r.invoice_outstanding_amount,
            r.invoice_gl_count, r.payment_entry_created, r.payment_entry_submitted,
            r.payment_entry_gl_count, r.executed_on, %(currency)s AS currency
        FROM `tabNDIS PE Smoke Invoice Source Run` r
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
                {"name": "Source Created", "values": [1 if row.status == "Source Created" else 0 for row in data[:20]]},
                {"name": "Invoice GL", "values": [int(row.invoice_gl_count or 0) for row in data[:20]]},
                {"name": "PE GL", "values": [int(row.payment_entry_gl_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Source Runs"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Source Created"]), "indicator": "Green", "label": _("Sources Created"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_created or 0) for row in data), "indicator": "Red", "label": _("Payment Entries Created"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count or 0) for row in data), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_source_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["source_run", "status", "severity", "category"]:
        if filters.get(fieldname):
            column = "i.source_run" if fieldname == "source_run" else f"i.{fieldname}"
            conditions.append(f"{column} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run Item", "width": 220},
        {"fieldname": "source_run", "label": _("Source Run"), "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 460},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.source_run, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype,
            i.source_name, i.checked_on
        FROM `tabNDIS PE Smoke Invoice Source Run Item` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_hygiene_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["si.custom_ndis_pe_smoke_source_invoice = 1"]
    params = {"currency": currency()}
    if filters.get("docstatus") not in [None, ""]:
        conditions.append("si.docstatus = %(docstatus)s")
        params["docstatus"] = int(filters.docstatus)
    if filters.get("outstanding_only"):
        conditions.append("si.outstanding_amount > 0")
    columns = [
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 80},
        {"fieldname": "source_run", "label": _("Source Run"), "fieldtype": "Link", "options": "NDIS PE Smoke Invoice Source Run", "width": 220},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 200},
        {"fieldname": "rounded_total", "label": _("Total"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_gl_count", "label": _("Invoice GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "pe_ref_count", "label": _("PE Ref Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "custom_ndis_pe_smoke_source_cancelled", "label": _("Source Cancelled"), "fieldtype": "Check", "width": 120},
        {"fieldname": "creation", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT si.name AS sales_invoice, si.docstatus,
            si.custom_ndis_pe_smoke_source_run AS source_run, si.customer,
            si.company, si.rounded_total, si.outstanding_amount,
            (SELECT COUNT(*) FROM `tabGL Entry` gl WHERE gl.voucher_type = 'Sales Invoice' AND gl.voucher_no = si.name) AS invoice_gl_count,
            (SELECT COUNT(*) FROM `tabPayment Entry Reference` per WHERE per.reference_doctype = 'Sales Invoice' AND per.reference_name = si.name) AS pe_ref_count,
            si.custom_ndis_pe_smoke_source_cancelled, si.creation, %(currency)s AS currency
        FROM `tabSales Invoice` si
        {build_where(conditions)}
        ORDER BY si.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Submitted", "Cancelled", "Draft"],
            "datasets": [
                {
                    "name": "Invoices",
                    "values": [
                        len([row for row in data if row.docstatus == 1]),
                        len([row for row in data if row.docstatus == 2]),
                        len([row for row in data if row.docstatus == 0]),
                    ],
                }
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Source Invoices"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 1]), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(flt(row.outstanding_amount) for row in data if row.docstatus == 1), "indicator": "Green", "label": _("Outstanding"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.pe_ref_count or 0) for row in data), "indicator": "Orange", "label": _("Payment Entry References"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    return " WHERE " + " AND ".join(conditions) if conditions else ""
