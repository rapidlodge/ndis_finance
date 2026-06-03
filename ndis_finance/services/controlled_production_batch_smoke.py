import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


RUN_DOCTYPE = "NDIS Controlled Production Batch Smoke Run"
LINE_DOCTYPE = "NDIS Controlled Production Batch Smoke Line"
SMOKE_ACK = "I_CONFIRM_PHASE8E_SUBMIT_ONE_CONTROLLED_PRODUCTION_BATCH_PAYMENT_ENTRY"


def make_smoke_run_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        return frappe.db.has_column(doctype, fieldname)
    except Exception:
        return bool(frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}))


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def submitted_phase8e_smoke_pe_count():
    if not has_column("Payment Entry", "custom_ndis_controlled_prod_batch_smoke"):
        return 0
    return count_dt("Payment Entry", {"docstatus": 1, "custom_ndis_controlled_prod_batch_smoke": 1})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
        "submitted_phase8e_smoke_pe_count": submitted_phase8e_smoke_pe_count(),
    }


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Activation Gate",
        filters={
            "status": "Activation Allowed",
            "activation_allowed_for_controlled_smoke": 1,
            "ready_for_controlled_batch_smoke": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "adapter_run",
            "preview",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "bank_account",
            "receivable_account",
            "max_batch_lines",
            "max_batch_amount",
            "would_create_payment_entry_count",
            "would_create_payment_entry_amount",
            "would_create_reference_count",
            "hard_blocked_line_count",
            "validation_blocked_line_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_submitted_smoke_for_gate(activation_gate):
    rows = frappe.get_all(
        RUN_DOCTYPE,
        filters={
            "activation_gate": activation_gate,
            "controlled_smoke_submitted": 1,
            "rollback_required": 1,
            "status": "Submitted - Rollback Required",
        },
        fields=["name", "smoke_run_id", "payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def get_adapter_lines(adapter_run):
    if not adapter_run:
        return []
    return frappe.get_all(
        "NDIS Controlled Production Batch Adapter Line",
        filters={
            "adapter_run": adapter_run,
            "line_status": "Hard Blocked",
            "would_create_reference": 1,
            "would_create_payment_entry": 1,
            "hard_block_applied": 1,
        },
        fields=[
            "name",
            "line_no",
            "preview",
            "preview_line",
            "source_run",
            "sales_invoice",
            "claim_line",
            "remittance_line",
            "invoice_outstanding",
            "allocatable_amount",
            "shortfall_amount",
        ],
        order_by="line_no asc, creation asc",
        limit=1000,
    )


def active_payment_entry_for_invoice(sales_invoice):
    rows = frappe.db.sql(
        """
        SELECT pe.name, pe.docstatus
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
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


def pe_gl_count_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type = 'Payment Entry'
            AND voucher_no = %(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def account_currency(account, fallback):
    if account and frappe.db.exists("Account", account):
        return frappe.db.get_value("Account", account, "account_currency") or fallback
    return fallback


def company_currency(company):
    return frappe.db.get_value("Company", company, "default_currency") or currency()


def resolve_bank_account(bank_account_ledger, company):
    if not frappe.db.exists("DocType", "Bank Account") or not bank_account_ledger:
        return None
    rows = frappe.get_all(
        "Bank Account",
        filters={"account": bank_account_ledger, "company": company},
        fields=["name", "is_default"],
        order_by="is_default desc, creation asc",
        limit=1,
    )
    return rows[0].name if rows else None


def validate_smoke_source(activation, lines):
    issues = []
    if not activation:
        return ["No approved Phase 8D activation gate found."]

    if existing_submitted_smoke_for_gate(activation.name):
        issues.append("A submitted Phase 8E smoke already exists for this activation gate.")
    if int(activation.would_create_payment_entry_count or 0) != 1:
        issues.append("Activation gate would_create_payment_entry_count is not 1.")
    if flt(activation.would_create_payment_entry_amount or 0) <= 0:
        issues.append("Activation gate would_create_payment_entry_amount is not positive.")
    if not resolve_bank_account(activation.bank_account, activation.company):
        issues.append("No Bank Account record is linked to the activation gate bank ledger account.")
    if not lines:
        issues.append("No hard-blocked adapter lines found.")
    if len(lines) != int(activation.would_create_reference_count or 0):
        issues.append("Adapter line count does not match activation would_create_reference_count.")

    total = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)
    if total != flt(activation.would_create_payment_entry_amount or 0, 2):
        issues.append(f"Adapter line total {total} does not match activation amount {flt(activation.would_create_payment_entry_amount or 0, 2)}.")
    if len(lines) > int(activation.max_batch_lines or 0):
        issues.append("Adapter line count exceeds max batch lines.")
    if total > flt(activation.max_batch_amount or 0):
        issues.append("Adapter amount exceeds max batch amount.")

    seen = set()
    for line in lines:
        if not line.sales_invoice:
            issues.append(f"Line {line.line_no}: Sales Invoice missing.")
            continue
        if line.sales_invoice in seen:
            issues.append(f"Line {line.line_no}: Duplicate Sales Invoice {line.sales_invoice}.")
        seen.add(line.sales_invoice)
        if not frappe.db.exists("Sales Invoice", line.sales_invoice):
            issues.append(f"Line {line.line_no}: Sales Invoice does not exist.")
            continue

        si = frappe.get_doc("Sales Invoice", line.sales_invoice)
        if si.docstatus != 1:
            issues.append(f"Line {line.line_no}: Sales Invoice is not submitted.")
        if si.company != activation.company:
            issues.append(f"Line {line.line_no}: Sales Invoice company mismatch.")
        if flt(si.outstanding_amount or 0) <= 0:
            issues.append(f"Line {line.line_no}: Sales Invoice has no outstanding amount.")
        if flt(line.allocatable_amount or 0) <= 0:
            issues.append(f"Line {line.line_no}: Allocatable amount is not positive.")
        if flt(line.allocatable_amount or 0) > flt(si.outstanding_amount or 0):
            issues.append(f"Line {line.line_no}: Allocatable amount exceeds invoice outstanding.")

        existing = active_payment_entry_for_invoice(si.name)
        if existing:
            issues.append(f"Line {line.line_no}: Active Payment Entry already exists for invoice {si.name}: {existing.name}.")

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
        }
    )


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def build_items(activation, lines, config, guard, source_issues, ack_ok):
    items = []
    if activation:
        add_item(items, "Pass", "Low", "Activation", "activation_exists", "Phase 8D activation gate exists", f"Activation gate found: {activation.activation_gate_id}.")
    else:
        add_item(items, "Blocker", "Critical", "Activation", "activation_exists", "Phase 8D activation gate exists", "No approved activation gate found.")

    if source_issues:
        for issue in source_issues:
            add_item(items, "Blocker", "Critical", "Source", "source_valid", "Smoke source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Source", "source_valid", "Smoke source valid", f"{len(lines)} source lines validated.")

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config remains disabled.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if guard["submitted_phase8e_smoke_pe_count"] == 0:
        add_item(items, "Pass", "Low", "Duplicate", "submitted_smoke_pe_zero", "No active Phase 8E smoke PE", "No submitted Phase 8E smoke Payment Entry exists.")
    else:
        add_item(items, "Blocker", "Critical", "Duplicate", "submitted_smoke_pe_zero", "No active Phase 8E smoke PE", f"{guard['submitted_phase8e_smoke_pe_count']} submitted Phase 8E smoke PE exists.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "smoke_ack", "Smoke acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "smoke_ack", "Smoke acknowledgement", f"Required acknowledgement not supplied: {SMOKE_ACK}")

    return items


def set_if_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def create_payment_entry_for_smoke(smoke_run, activation, lines):
    amount = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)
    ccy = company_currency(activation.company)

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = activation.company
    pe.posting_date = today()
    pe.party_type = "Customer"
    pe.party = activation.customer
    pe.paid_from = activation.receivable_account
    pe.paid_to = activation.bank_account
    set_if_field(pe, "bank_account", resolve_bank_account(activation.bank_account, activation.company))
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.reference_no = smoke_run
    pe.reference_date = today()
    pe.remarks = f"Phase 8E controlled production batch smoke. Rollback required immediately. Smoke Run: {smoke_run}"

    set_if_field(pe, "custom_ndis_controlled_prod_batch_smoke", 1)
    set_if_field(pe, "custom_ndis_controlled_prod_batch_smoke_run", smoke_run)
    set_if_field(pe, "custom_ndis_controlled_prod_batch_activation_gate", activation.name)
    set_if_field(pe, "custom_ndis_controlled_prod_batch_adapter_run", activation.adapter_run)
    set_if_field(pe, "custom_ndis_controlled_prod_batch_preview", activation.preview)
    set_if_field(pe, "paid_from_account_currency", account_currency(activation.receivable_account, ccy))
    set_if_field(pe, "paid_to_account_currency", account_currency(activation.bank_account, ccy))
    set_if_field(pe, "source_exchange_rate", 1)
    set_if_field(pe, "target_exchange_rate", 1)

    for line in lines:
        si = frappe.get_doc("Sales Invoice", line.sales_invoice)
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": si.name,
                "total_amount": flt(si.rounded_total or si.grand_total or 0),
                "outstanding_amount": flt(si.outstanding_amount or 0),
                "allocated_amount": flt(line.allocatable_amount or 0),
            },
        )

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


def create_smoke_line(smoke_run, activation, line, payment_entry, status="Submitted", detail=None):
    invoice_after = 0
    if line.sales_invoice and frappe.db.exists("Sales Invoice", line.sales_invoice):
        invoice_after = flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0)

    doc = frappe.new_doc(LINE_DOCTYPE)
    doc.smoke_run = smoke_run
    doc.line_no = line.line_no
    doc.line_label = f"Phase 8E Smoke Line {line.line_no}"
    doc.line_status = status
    doc.status_detail = detail or "Payment Entry reference submitted."
    doc.activation_gate = activation.name
    doc.adapter_run = activation.adapter_run
    doc.adapter_line = line.name
    doc.preview = line.preview
    doc.preview_line = line.preview_line
    doc.sales_invoice = line.sales_invoice
    doc.claim_line = line.claim_line
    doc.remittance_line = line.remittance_line
    doc.invoice_outstanding_before = flt(line.invoice_outstanding or 0)
    doc.allocated_amount = flt(line.allocatable_amount or 0)
    doc.invoice_outstanding_after = invoice_after
    doc.shortfall_amount = flt(line.shortfall_amount or 0)
    doc.payment_entry = payment_entry
    doc.payment_entry_reference_created = 1 if payment_entry and status == "Submitted" else 0
    doc.checked_on = now_datetime()
    doc.insert(ignore_permissions=True)


@frappe.whitelist()
def run_controlled_production_batch_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_smoke")

    activation = latest_activation_gate()
    lines = get_adapter_lines(activation.adapter_run) if activation else []
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    source_issues = validate_smoke_source(activation, lines)
    items = build_items(activation, lines, config, guard_before, source_issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    amount = flt(sum(flt(line.allocatable_amount or 0) for line in lines), 2)
    outstanding_before = flt(sum(flt(line.invoice_outstanding or 0) for line in lines), 2)
    can_submit = bool(ack_ok and item_summary["blocker_count"] == 0 and activation and lines)

    base_result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Submitted - Rollback Required" if can_submit else "Needs Review",
        "smoke_status": "Submitted - Rollback Required" if can_submit else "Needs Review",
        "controlled_smoke_submitted": 1 if can_submit else 0,
        "rollback_required": 1 if can_submit else 0,
        "freeze_required_after_rollback": 1 if can_submit else 0,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "activation_gate": activation.name if activation else None,
        "adapter_run": activation.adapter_run if activation else None,
        "preview": activation.preview if activation else None,
        "design_gate": activation.design_gate if activation else None,
        "phase7h_freeze": activation.phase7h_freeze if activation else None,
        "source_run": activation.source_run if activation else None,
        "company": activation.company if activation else None,
        "customer": activation.customer if activation else None,
        "bank_account": activation.bank_account if activation else None,
        "receivable_account": activation.receivable_account if activation else None,
        "payment_entry": None,
        "payment_entry_created": 0,
        "payment_entry_submitted": 0,
        "payment_entry_docstatus": 0,
        "payment_entry_amount": amount,
        "invoice_count": len(lines),
        "payment_entry_reference_count": len(lines),
        "invoice_outstanding_before_total": outstanding_before,
        "invoice_outstanding_after_total": outstanding_before,
        "payment_entry_gl_count": 0,
        "payment_entry_gl_net": 0,
        "smoke_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8E submits exactly one controlled Payment Entry and marks rollback required immediately.",
    }

    if int(dry_run or 0):
        base_result.update(
            {
                "status": "Needs Review",
                "smoke_status": "Needs Review",
                "controlled_smoke_submitted": 0,
                "rollback_required": 0,
                "freeze_required_after_rollback": 0,
            }
        )
        return base_result

    doc = frappe.new_doc(RUN_DOCTYPE)
    doc.smoke_run_id = make_smoke_run_id()
    doc.status = "Needs Review"
    doc.smoke_status = "Needs Review"
    doc.controlled_smoke_submitted = 0
    doc.rollback_required = 0
    doc.freeze_required_after_rollback = 0
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0

    for fieldname in [
        "activation_gate",
        "adapter_run",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "bank_account",
        "receivable_account",
        "payment_entry_amount",
        "invoice_count",
        "payment_entry_reference_count",
        "invoice_outstanding_before_total",
        "invoice_outstanding_after_total",
        "payment_entry_gl_count",
        "payment_entry_gl_net",
        "smoke_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, base_result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_before["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guard_before["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]
    doc.required_acknowledgement = SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(base_result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    if not can_submit:
        base_result.update({"created": True, "smoke_run": doc.name, "smoke_run_id": doc.smoke_run_id})
        return base_result

    try:
        payment_entry = create_payment_entry_for_smoke(doc.name, activation, lines)

        for line in lines:
            create_smoke_line(doc.name, activation, line, payment_entry)

        invoice_after = flt(sum(flt(frappe.db.get_value("Sales Invoice", line.sales_invoice, "outstanding_amount") or 0) for line in lines), 2)
        pe_gl_count, pe_gl_net = pe_gl_count_net(payment_entry)
        pe_docstatus = int(frappe.db.get_value("Payment Entry", payment_entry, "docstatus") or 0)
        guard_after = guardrails()

        update_values = {
            "status": "Submitted - Rollback Required",
            "smoke_status": "Submitted - Rollback Required",
            "controlled_smoke_submitted": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "payment_entry": payment_entry,
            "payment_entry_created": 1,
            "payment_entry_submitted": 1 if pe_docstatus == 1 else 0,
            "payment_entry_docstatus": pe_docstatus,
            "invoice_outstanding_after_total": invoice_after,
            "payment_entry_gl_count": pe_gl_count,
            "payment_entry_gl_net": pe_gl_net,
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        }
        result = {
            **base_result,
            **update_values,
            "created": True,
            "smoke_run": doc.name,
            "smoke_run_id": doc.smoke_run_id,
            "payment_entry": payment_entry,
            "guardrails_after": guard_after,
        }
        update_values["summary_json"] = safe_json(result)
        frappe.db.set_value(RUN_DOCTYPE, doc.name, update_values, update_modified=False)
        frappe.db.commit()
        return result
    except Exception as exc:
        frappe.db.rollback()
        frappe.db.set_value(
            RUN_DOCTYPE,
            doc.name,
            {
                "status": "Failed",
                "smoke_status": "Failed",
                "controlled_smoke_submitted": 0,
                "rollback_required": 0,
                "freeze_required_after_rollback": 0,
                "summary_json": safe_json({"error": str(exc), **base_result}),
            },
            update_modified=False,
        )
        frappe.db.commit()
        raise


@frappe.whitelist()
def cancel_controlled_production_batch_smoke_audit(smoke_run, reason=None):
    assert_action("cancel_controlled_production_batch_smoke_audit")

    if not frappe.db.exists(RUN_DOCTYPE, smoke_run):
        frappe.throw(_("Smoke run not found: {0}").format(smoke_run))

    doc = frappe.get_doc(RUN_DOCTYPE, smoke_run)
    if doc.status == "Cancelled":
        return {"smoke_run": smoke_run, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.controlled_smoke_submitted or 0) or doc.payment_entry:
        frappe.throw(_("Cannot cancel a submitted smoke run here. Use the Phase 8F rollback phase."))

    frappe.db.set_value(
        RUN_DOCTYPE,
        smoke_run,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "controlled_smoke_submitted": 0,
            "rollback_required": 0,
            "freeze_required_after_rollback": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 8E smoke audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{LINE_DOCTYPE}` SET line_status = 'Cancelled' WHERE smoke_run = %(smoke_run)s", {"smoke_run": smoke_run})
    frappe.db.commit()
    return {
        "smoke_run": smoke_run,
        "status": "Cancelled",
        "note": "Smoke audit record cancelled only. No submitted Payment Entry was cancelled here.",
    }


@frappe.whitelist()
def quick_controlled_production_batch_smoke_summary(limit=20):
    runs = frappe.get_all(
        RUN_DOCTYPE,
        fields=[
            "name",
            "smoke_run_id",
            "status",
            "smoke_status",
            "controlled_smoke_submitted",
            "rollback_required",
            "freeze_required_after_rollback",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "activation_gate",
            "adapter_run",
            "preview",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_submitted",
            "payment_entry_docstatus",
            "payment_entry_amount",
            "invoice_count",
            "payment_entry_reference_count",
            "invoice_outstanding_before_total",
            "invoice_outstanding_after_total",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        LINE_DOCTYPE,
        fields=[
            "name",
            "smoke_run",
            "line_no",
            "line_status",
            "sales_invoice",
            "payment_entry",
            "invoice_outstanding_before",
            "allocated_amount",
            "invoice_outstanding_after",
            "payment_entry_reference_created",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "runs": runs,
        "lines": lines,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 8E smoke summary. Submitted smoke must be rolled back in Phase 8F.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = smoke_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke_run,
            s.smoke_run_id,
            s.status,
            s.smoke_status,
            s.controlled_smoke_submitted,
            s.rollback_required,
            s.freeze_required_after_rollback,
            s.production_batch_posting_allowed,
            s.real_posting_allowed,
            s.activation_gate,
            s.payment_entry,
            s.payment_entry_submitted,
            s.payment_entry_docstatus,
            s.payment_entry_amount,
            s.invoice_count,
            s.invoice_outstanding_before_total,
            s.invoice_outstanding_after_total,
            s.payment_entry_gl_count,
            s.payment_entry_gl_net,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tab{RUN_DOCTYPE}` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.smoke_run_id for row in data[:20]],
            "datasets": [
                {"name": "Submitted", "values": [int(row.controlled_smoke_submitted or 0) for row in data[:20]]},
                {"name": "Rollback Required", "values": [int(row.rollback_required or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smoke Runs"), "datatype": "Int"},
        {"value": sum(int(row.controlled_smoke_submitted or 0) for row in data), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(flt(row.payment_entry_amount or 0) for row in data), "indicator": "Blue", "label": _("Payment Amount"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def smoke_columns():
    return [
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run_id", "label": _("Smoke Run ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_entry_submitted", "label": _("PE Submitted"), "fieldtype": "Check", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
        {"fieldname": "invoice_outstanding_before_total", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "invoice_outstanding_after_total", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 130},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("smoke_run"):
        conditions.append("l.smoke_run = %(smoke_run)s")
        params["smoke_run"] = filters.get("smoke_run")
    if filters.get("line_status"):
        conditions.append("l.line_status = %(line_status)s")
        params["line_status"] = filters.get("line_status")

    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": LINE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_run", "label": _("Smoke Run"), "fieldtype": "Link", "options": RUN_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "invoice_outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "invoice_outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_reference_created", "label": _("PE Ref Created"), "fieldtype": "Check", "width": 120},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            l.name AS line,
            l.smoke_run,
            l.line_no,
            l.line_status,
            l.sales_invoice,
            l.payment_entry,
            l.invoice_outstanding_before,
            l.allocated_amount,
            l.invoice_outstanding_after,
            l.payment_entry_reference_created,
            %(currency)s AS currency
        FROM `tab{LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.smoke_run DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [str(row.line_no) for row in data[:20]],
            "datasets": [{"name": "Allocated", "values": [flt(row.allocated_amount or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.line_status == "Submitted"]), "indicator": "Green", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0) for row in data), "indicator": "Blue", "label": _("Allocated"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_phase8e_smoke_pe_count"], "indicator": "Orange", "label": _("Submitted Phase 8E Smoke PE"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
