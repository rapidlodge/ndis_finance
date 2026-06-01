import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS Real Remittance PE Smoke Run"
LINE_DOCTYPE = "NDIS Real Remittance PE Smoke Line"
SMOKE_ACK = "I_CONFIRM_PHASE6F_SUBMIT_ONE_CONTROLLED_REMITTANCE_PAYMENT_ENTRY"


def make_smoke_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_ready_activation_gate():
    rows = frappe.get_all(
        "NDIS Real Remittance PE Activation Gate",
        filters={
            "status": "Activation Allowed",
            "ready_for_real_smoke": 1,
            "structural_ready_allowed": 1,
            "real_posting_allowed": 0,
            "source_eligible_pending": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "adapter_run",
            "preview",
            "source_remittance_import",
            "company",
            "bank_account",
            "receivable_account",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def latest_source_harness():
    rows = frappe.get_all(
        "NDIS Real Remittance PE Source Harness Run",
        filters={
            "status": "Source Ready",
            "source_ready_for_preview": 1,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "harness_run_id",
            "company",
            "customer",
            "sales_invoice",
            "claim_line",
            "remittance_import",
            "remittance_line",
            "source_amount",
            "invoice_outstanding_before_payment",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


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


def pe_reference_count(payment_entry=None, sales_invoice=None, active_only=False):
    conditions = []
    params = {}
    if payment_entry:
        conditions.append("per.parent = %(payment_entry)s")
        params["payment_entry"] = payment_entry
    if sales_invoice:
        conditions.append("per.reference_doctype = 'Sales Invoice'")
        conditions.append("per.reference_name = %(sales_invoice)s")
        params["sales_invoice"] = sales_invoice
    join = ""
    if active_only:
        join = "INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent"
        conditions.append("pe.docstatus != 2")
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tabPayment Entry Reference` per
        {join}
        WHERE {where_clause}
        """,
        params,
    )[0][0]


def active_payment_entry_for_invoice(sales_invoice):
    if not sales_invoice:
        return None
    rows = frappe.db.sql(
        """
        SELECT pe.name, pe.docstatus
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Invoice'
        AND per.reference_name = %(sales_invoice)s
        AND pe.docstatus != 2
        ORDER BY pe.creation DESC
        LIMIT 1
        """,
        {"sales_invoice": sales_invoice},
        as_dict=True,
    )
    return rows[0] if rows else None


def account_doc(account):
    if not account or not frappe.db.exists("Account", account):
        return None
    return frappe.get_doc("Account", account)


def validate_account(account, company, label):
    doc = account_doc(account)
    if not doc:
        frappe.throw(_("{0} is missing or invalid: {1}").format(label, account))
    if doc.company != company:
        frappe.throw(_("{0} does not belong to company {1}: {2}").format(label, company, account))
    if int(doc.is_group or 0):
        frappe.throw(_("{0} is a group account: {1}").format(label, account))
    if int(doc.disabled or 0):
        frappe.throw(_("{0} is disabled: {1}").format(label, account))


def set_if_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)
        return True
    return False


def bank_account_for_ledger(account, company):
    rows = frappe.get_all(
        "Bank Account",
        filters={"account": account, "company": company, "is_company_account": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if rows:
        return rows[0].name
    rows = frappe.get_all(
        "Bank Account",
        filters={"account": account, "company": company},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


def validate_ready_source(gate, harness):
    if not gate:
        frappe.throw(_("No Phase 6D Activation Allowed gate found. Complete Phase 6D after Phase 6E."))
    if not harness:
        frappe.throw(_("No Phase 6E source-ready harness found."))
    if not gate.bank_account or not gate.receivable_account:
        frappe.throw(_("Phase 6D gate is missing locked bank or receivable account."))
    validate_account(gate.bank_account, gate.company, "Bank account")
    validate_account(gate.receivable_account, gate.company, "Receivable account")
    if not bank_account_for_ledger(gate.bank_account, gate.company):
        frappe.throw(_("No ERPNext Bank Account is linked to locked ledger account {0}.").format(gate.bank_account))
    if not harness.sales_invoice or not frappe.db.exists("Sales Invoice", harness.sales_invoice):
        frappe.throw(_("Controlled source Sales Invoice is missing."))

    si = frappe.get_doc("Sales Invoice", harness.sales_invoice)
    if si.docstatus != 1:
        frappe.throw(_("Controlled source Sales Invoice must be submitted before Phase 6F."))
    if not int(getattr(si, "custom_ndis_real_remittance_pe_harness_invoice", 0) or 0):
        frappe.throw(_("Sales Invoice is not tagged as a Phase 6E controlled harness invoice."))
    if si.company != gate.company:
        frappe.throw(_("Sales Invoice company does not match Phase 6D gate company."))
    if flt(si.outstanding_amount) <= 0:
        frappe.throw(_("Controlled source Sales Invoice has no outstanding balance."))
    if flt(si.outstanding_amount, 2) != 1:
        frappe.throw(_("Phase 6F expects exactly 1.00 outstanding on the controlled source Sales Invoice."))

    existing = active_payment_entry_for_invoice(si.name)
    if existing:
        frappe.throw(_("An active Payment Entry already exists for controlled invoice {0}: {1}").format(si.name, existing.name))
    return si


def create_smoke_line(smoke_run, record_type, record_doctype, record_name, label, status="Info", amount=0, detail=None):
    row = frappe.new_doc(LINE_DOCTYPE)
    row.smoke_run = smoke_run
    row.record_type = record_type
    row.record_doctype = record_doctype
    row.record_name = record_name
    row.record_label = label
    row.status = status
    row.amount = flt(amount or 0)
    row.detail = detail
    row.checked_on = now_datetime()
    row.insert(ignore_permissions=True)


def create_payment_entry(run_doc, gate, harness, si):
    amount = flt(si.outstanding_amount, 2)
    company_currency = frappe.get_cached_value("Company", gate.company, "default_currency") or currency()
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = gate.company
    pe.posting_date = today()
    pe.bank_account = bank_account_for_ledger(gate.bank_account, gate.company)
    pe.party_type = "Customer"
    pe.party = si.customer
    pe.paid_from = gate.receivable_account
    pe.paid_to = gate.bank_account
    pe.paid_from_account_currency = company_currency
    pe.paid_to_account_currency = company_currency
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.base_paid_amount = amount
    pe.base_received_amount = amount
    pe.reference_no = run_doc.smoke_run_id
    pe.reference_date = today()
    pe.remarks = "Phase 6F controlled one-record real remittance Payment Entry smoke."
    set_if_field(pe, "custom_ndis_real_remittance_pe_smoke", 1)
    set_if_field(pe, "custom_ndis_real_remittance_pe_smoke_run", run_doc.name)
    set_if_field(pe, "custom_ndis_real_remittance_pe_harness_run", harness.name)
    set_if_field(pe, "custom_ndis_real_remittance_pe_source_invoice", si.name)
    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": si.name,
            "allocated_amount": amount,
            "total_amount": flt(si.grand_total),
            "outstanding_amount": flt(si.outstanding_amount),
        },
    )
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


@frappe.whitelist()
def run_one_real_remittance_pe_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_one_real_remittance_pe_smoke")
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK
    gate = latest_ready_activation_gate()
    harness = latest_source_harness()
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "acknowledgement_ok": ack_ok,
        "required_acknowledgement": SMOKE_ACK,
        "activation_gate": gate.name if gate else None,
        "source_harness_run": harness.name if harness else None,
        "real_posting_allowed": 0,
        "single_record_smoke_allowed": 0,
        "payment_entry_created": 0,
        "payment_entry_submitted": 0,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "note": "Phase 6F submits exactly one controlled Payment Entry only when exact acknowledgement and source controls pass.",
    }
    if int(dry_run or 0):
        result["status"] = "Previewed"
        return result

    run = frappe.new_doc(RUN_DOCTYPE)
    run.smoke_run_id = make_smoke_run_id()
    run.status = "Needs Review"
    run.smoke_type = "One Controlled Real Remittance Payment Entry"
    run.single_record_smoke_allowed = 0
    run.payment_entry_created = 0
    run.payment_entry_submitted = 0
    run.real_posting_allowed = 0
    run.activation_gate = gate.name if gate else None
    run.adapter_run = gate.adapter_run if gate else None
    run.preview = gate.preview if gate else None
    run.source_harness_run = harness.name if harness else None
    run.sales_invoice = harness.sales_invoice if harness else None
    run.remittance_import = harness.remittance_import if harness else None
    run.remittance_line = harness.remittance_line if harness else None
    run.company = gate.company if gate else None
    run.customer = harness.customer if harness else None
    run.bank_account = gate.bank_account if gate else None
    run.receivable_account = gate.receivable_account if gate else None
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
    run.required_acknowledgement = SMOKE_ACK
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
        result.update(
            {
                "created": True,
                "smoke_run": run.name,
                "smoke_run_id": run.smoke_run_id,
                "status": run.status,
                "guardrails_after": guard_after,
            }
        )
        return result

    if config["production_mode"]:
        frappe.throw(_("Production mode config is enabled. Refusing Phase 6F smoke."))
    if config["live_pe_enabled"]:
        frappe.throw(_("Global live PE posting config is enabled. Phase 6F expects it to remain disabled."))
    if guard_before["live_enabled_policy_count"]:
        frappe.throw(_("Live-enabled PE policy exists. Refusing Phase 6F smoke."))

    si = validate_ready_source(gate, harness)
    run.invoice_outstanding_before = flt(si.outstanding_amount)
    run.payment_amount = flt(si.outstanding_amount)
    run.single_record_smoke_allowed = 1
    run.insert(ignore_permissions=True)
    create_smoke_line(run.name, "Source Invoice", "Sales Invoice", si.name, "Controlled source Sales Invoice before payment", "Validated", flt(si.outstanding_amount), "Submitted Phase 6E controlled harness invoice validated.")

    payment_entry = create_payment_entry(run, gate, harness, si)
    si.reload()
    pe = frappe.get_doc("Payment Entry", payment_entry)
    guard_after = guardrails()
    pe_gl_count = gl_count("Payment Entry", payment_entry)
    pe_gl_net = gl_net("Payment Entry", payment_entry)
    pe_ref_count = pe_reference_count(payment_entry=payment_entry)

    create_smoke_line(run.name, "Payment Entry", "Payment Entry", payment_entry, "Controlled submitted Payment Entry", "Submitted", flt(pe.paid_amount), "Exactly one controlled Payment Entry submitted by Phase 6F.")
    create_smoke_line(run.name, "Sales Invoice", "Sales Invoice", si.name, "Controlled source Sales Invoice after payment", "Linked", flt(si.outstanding_amount), "Invoice outstanding reloaded after submitted Payment Entry.")

    run.status = "Submitted"
    run.payment_entry_created = 1
    run.payment_entry_submitted = 1
    run.real_posting_allowed = 0
    run.payment_entry = payment_entry
    run.payment_entry_docstatus = pe.docstatus
    run.payment_entry_gl_count = pe_gl_count
    run.payment_entry_gl_net = pe_gl_net
    run.payment_entry_reference_count = pe_ref_count
    run.invoice_outstanding_after = flt(si.outstanding_amount)
    run.payment_entry_count_after = guard_after["payment_entry_count"]
    run.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]
    result.update(
        {
            "created": True,
            "smoke_run": run.name,
            "smoke_run_id": run.smoke_run_id,
            "status": run.status,
            "single_record_smoke_allowed": 1,
            "payment_entry": payment_entry,
            "payment_entry_created": 1,
            "payment_entry_submitted": 1,
            "payment_entry_docstatus": pe.docstatus,
            "payment_amount": flt(pe.paid_amount),
            "sales_invoice": si.name,
            "invoice_outstanding_before": flt(run.invoice_outstanding_before),
            "invoice_outstanding_after": flt(si.outstanding_amount),
            "payment_entry_gl_count": pe_gl_count,
            "payment_entry_gl_net": pe_gl_net,
            "payment_entry_reference_count": pe_ref_count,
            "guardrails_after": guard_after,
        }
    )
    run.summary_json = safe_json(result)
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_one_real_remittance_pe_smoke_audit(smoke_run, reason=None):
    assert_action("cancel_one_real_remittance_pe_smoke_audit")
    if not frappe.db.exists(RUN_DOCTYPE, smoke_run):
        frappe.throw(_("Smoke run not found: {0}").format(smoke_run))
    doc = frappe.get_doc(RUN_DOCTYPE, smoke_run)
    if doc.payment_entry or int(doc.payment_entry_created or 0):
        frappe.throw(_("Cannot cancel a Phase 6F run that created a Payment Entry. Use the controlled rollback phase next."))
    frappe.db.set_value(
        RUN_DOCTYPE,
        smoke_run,
        {
            "status": "Cancelled",
            "single_record_smoke_allowed": 0,
            "payment_entry_created": 0,
            "payment_entry_submitted": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6F audit-only smoke run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET status = 'Cancelled' WHERE smoke_run = %(smoke_run)s", {"smoke_run": smoke_run})
    frappe.db.commit()
    return {"smoke_run": smoke_run, "status": "Cancelled", "note": "Audit-only Phase 6F run cancelled. No Payment Entry was changed."}


@frappe.whitelist()
def quick_real_remittance_pe_smoke_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "smoke_run_id",
            "status",
            "single_record_smoke_allowed",
            "payment_entry_created",
            "payment_entry_submitted",
            "real_posting_allowed",
            "sales_invoice",
            "payment_entry",
            "payment_amount",
            "invoice_outstanding_before",
            "invoice_outstanding_after",
            "payment_entry_docstatus",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
            "payment_entry_reference_count",
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
        fields=["name", "smoke_run", "record_type", "record_doctype", "record_name", "record_label", "status", "amount", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6F summary. Exactly one controlled Payment Entry should exist after the successful smoke.",
    }


def smoke_columns():
    return [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run_id", "label": _("Smoke Run ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "payment_entry_submitted", "label": _("PE Submitted"), "fieldtype": "Check", "width": 110},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_amount", "label": _("Payment Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_smoke_report(filters=None):
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
    data = frappe.db.sql(
        f"""
        SELECT r.name AS smoke_run, r.smoke_run_id, r.status, r.single_record_smoke_allowed,
            r.payment_entry_created, r.payment_entry_submitted, r.real_posting_allowed,
            r.sales_invoice, r.payment_entry, r.payment_amount, r.invoice_outstanding_before,
            r.invoice_outstanding_after, r.payment_entry_docstatus, r.payment_entry_gl_count,
            r.payment_entry_gl_net, r.payment_entry_reference_count, r.checked_on,
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
            "labels": [row.smoke_run_id for row in data[:20]],
            "datasets": [
                {"name": "PE Submitted", "values": [int(row.payment_entry_submitted or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_submitted or 0) for row in data), "indicator": "Green", "label": _("Submitted PEs"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return smoke_columns(), data, None, chart, summary


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("smoke_run"):
        conditions.append("l.smoke_run = %(smoke_run)s")
        params["smoke_run"] = filters.smoke_run
    if filters.get("record_type"):
        conditions.append("l.record_type = %(record_type)s")
        params["record_type"] = filters.record_type
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
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
        SELECT l.name AS line, l.smoke_run, l.record_type, l.record_doctype, l.record_name,
            l.status, l.amount, l.detail, l.checked_on, %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.record_type or "Unknown"] = chart_map.get(row.record_type or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Records", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Submitted"]), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
    summary.extend(
        [
            {
                "value": count_dt("Payment Entry", {"docstatus": 1, "custom_ndis_real_remittance_pe_smoke": 1}),
                "indicator": "Green",
                "label": _("Submitted Smoke PEs"),
                "datatype": "Int",
            },
            {
                "value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
                "indicator": "Red",
                "label": _("Submitted JEs Today"),
                "datatype": "Int",
            },
            {
                "value": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
                "indicator": "Red",
                "label": _("Purchase Invoices Today"),
                "datatype": "Int",
            },
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
