import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action
from ndis_finance.setup.phase4c import CLEANUP_LINE_DOCTYPE, CLEANUP_PACK_DOCTYPE


CLEANUP_ACK = "I_CONFIRM_CLEAN_PHASE4_SANDBOX_ACCOUNTING_EVIDENCE"


def make_pack_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-ACCT-CLEAN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def validate_sandbox_config():
    errors = []
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)

    if not sandbox_enabled:
        errors.append("Site config ndis_finance_sandbox_posting_enabled is not enabled.")
    if production_mode:
        errors.append("Site config ndis_finance_production_mode is enabled.")

    return {"sandbox_enabled": sandbox_enabled, "production_mode": production_mode, "errors": errors}


def gl_count(voucher_type, voucher_no):
    if not voucher_type or not voucher_no or not frappe.db.exists("DocType", "GL Entry"):
        return 0
    return frappe.db.count("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})


def gl_net(voucher_type, voucher_no):
    if not voucher_type or not voucher_no or not frappe.db.exists("DocType", "GL Entry"):
        return 0
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) AS net
        FROM `tabGL Entry`
        WHERE voucher_type = %(voucher_type)s
        AND voucher_no = %(voucher_no)s
        """,
        {"voucher_type": voucher_type, "voucher_no": voucher_no},
        as_dict=True,
    )
    return flt(result[0].net if result else 0)


def submitted_sandbox_pe_count():
    return frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1})


def submitted_pe_today():
    return frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1})


def pe_gl_today():
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0
    return frappe.db.count("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"})


def submitted_je_today():
    if not frappe.db.exists("DocType", "Journal Entry"):
        return 0
    return frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1})


def purchase_invoice_today():
    if not frappe.db.exists("DocType", "Purchase Invoice"):
        return 0
    return frappe.db.count("Purchase Invoice", {"creation": [">=", today()]})


def collect_post_guardrails():
    return {
        "submitted_sandbox_pe_count": submitted_sandbox_pe_count(),
        "submitted_payment_entry_count_today": submitted_pe_today(),
        "payment_entry_gl_count_today": pe_gl_today(),
        "submitted_journal_entry_count_today": submitted_je_today(),
        "purchase_invoice_count_today": purchase_invoice_today(),
    }


def find_payment_entry_candidates(target_payment_entry=None):
    filters = {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0}
    if target_payment_entry:
        filters["name"] = target_payment_entry
    return frappe.get_all(
        "Payment Entry",
        filters=filters,
        fields=[
            "name",
            "docstatus",
            "party",
            "party_type",
            "company",
            "paid_amount",
            "received_amount",
            "custom_ndis_sandbox_payment_entry_draft_only",
            "custom_ndis_sandbox_payment_entry_run",
            "custom_ndis_payment_entry_allocation_preview",
        ],
        order_by="creation desc",
        limit=10000,
    )


def find_sales_invoice_candidates(target_sales_invoice=None):
    filters = {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 1}
    if target_sales_invoice:
        filters["name"] = target_sales_invoice
    return frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "docstatus",
            "customer",
            "company",
            "outstanding_amount",
            "grand_total",
            "custom_ndis_sandbox_test_invoice",
            "custom_ndis_sandbox_invoice_test_run",
        ],
        order_by="creation desc",
        limit=10000,
    )


def payment_entry_references_invoice(sales_invoice, submitted_only=0):
    if not frappe.db.exists("DocType", "Payment Entry Reference"):
        return []
    return frappe.db.sql(
        """
        SELECT per.parent AS payment_entry, pe.docstatus, pe.custom_ndis_sandbox_payment_entry_draft_only
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Invoice'
        AND per.reference_name = %(sales_invoice)s
        {submitted_clause}
        """.format(submitted_clause="AND pe.docstatus = 1" if int(submitted_only or 0) else ""),
        {"sales_invoice": sales_invoice},
        as_dict=True,
    )


def evaluate_payment_entry_candidate(row):
    reasons = []
    if int(row.docstatus or 0) != 0:
        reasons.append("Payment Entry is not draft docstatus 0.")
    if not int(row.custom_ndis_sandbox_payment_entry_draft_only or 0):
        reasons.append("Payment Entry is not tagged as NDIS sandbox draft-only.")
    linked_gl = gl_count("Payment Entry", row.name)
    if linked_gl:
        reasons.append(f"Payment Entry has linked GL Entry count {linked_gl}.")
    return {
        "record_doctype": "Payment Entry",
        "record_name": row.name,
        "eligible": not bool(reasons),
        "block_reason": "; ".join(reasons),
        "docstatus_before": int(row.docstatus or 0),
        "docstatus_after": int(row.docstatus or 0),
        "linked_gl_before": linked_gl,
        "linked_gl_after": linked_gl,
        "gl_net_after": 0,
        "amount": flt(row.paid_amount or row.received_amount),
    }


def evaluate_sales_invoice_candidate(row):
    reasons = []
    if int(row.docstatus or 0) != 1:
        reasons.append("Sales Invoice is not submitted docstatus 1.")
    if not int(row.custom_ndis_sandbox_test_invoice or 0):
        reasons.append("Sales Invoice is not tagged as NDIS sandbox test invoice.")
    if payment_entry_references_invoice(row.name, submitted_only=1):
        reasons.append("Submitted Payment Entry references this Sales Invoice.")
    linked_gl = gl_count("Sales Invoice", row.name)
    return {
        "record_doctype": "Sales Invoice",
        "record_name": row.name,
        "eligible": not bool(reasons),
        "block_reason": "; ".join(reasons),
        "docstatus_before": int(row.docstatus or 0),
        "docstatus_after": int(row.docstatus or 0),
        "linked_gl_before": linked_gl,
        "linked_gl_after": linked_gl,
        "gl_net_after": gl_net("Sales Invoice", row.name),
        "amount": flt(row.outstanding_amount or row.grand_total),
    }


def create_pack(status, cleanup_scope, target_payment_entry, target_sales_invoice, cleanup_payment_entries, cancel_submitted_invoices, acknowledgement, validation, notes=None):
    pack = frappe.new_doc(CLEANUP_PACK_DOCTYPE)
    pack.pack_id = make_pack_id()
    pack.status = status
    pack.cleanup_scope = cleanup_scope
    pack.sandbox_only = 1
    pack.target_payment_entry = target_payment_entry
    pack.target_sales_invoice = target_sales_invoice
    pack.cleanup_payment_entries = int(cleanup_payment_entries or 0)
    pack.cancel_submitted_invoices = int(cancel_submitted_invoices or 0)
    pack.site_name = frappe.local.site
    pack.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    pack.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    pack.required_acknowledgement = CLEANUP_ACK
    pack.acknowledgement = acknowledgement
    pack.acknowledgement_ok = int(acknowledgement == CLEANUP_ACK)
    pack.created_on = now_datetime()
    pack.created_by_user = frappe.session.user
    pack.validation_log = safe_json(validation)
    pack.notes = notes
    pack.insert(ignore_permissions=True)
    return pack


def add_line(pack, status, severity, action_type, candidate, record_exists_after, action_taken=None, block_reason=None):
    line = frappe.new_doc(CLEANUP_LINE_DOCTYPE)
    line.cleanup_pack = pack.name
    line.status = status
    line.severity = severity
    line.action_type = action_type
    line.record_doctype = candidate["record_doctype"]
    line.record_name = candidate["record_name"]
    line.record_exists_before = 1
    line.record_exists_after = int(record_exists_after or 0)
    line.docstatus_before = candidate["docstatus_before"]
    line.docstatus_after = candidate["docstatus_after"]
    line.linked_gl_count_before = int(candidate["linked_gl_before"] or 0)
    line.linked_gl_count_after = int(candidate["linked_gl_after"] or 0)
    line.gl_net_after = flt(candidate["gl_net_after"] or 0)
    line.amount = flt(candidate["amount"] or 0)
    line.block_reason = block_reason if block_reason is not None else candidate.get("block_reason")
    line.action_taken = action_taken
    line.insert(ignore_permissions=True)
    return line


def clear_sandbox_pe_run_link(payment_entry):
    for row in frappe.get_all("NDIS Sandbox Payment Entry Run", filters={"payment_entry": payment_entry}, fields=["name"], limit=100):
        frappe.db.set_value(
            "NDIS Sandbox Payment Entry Run",
            row.name,
            {
                "payment_entry": None,
                "payment_entry_docstatus": 0,
                "validation_log": f"Draft sandbox Payment Entry {payment_entry} deleted by Phase 4C cleanup pack.",
            },
            update_modified=False,
        )


def delete_payment_entry(payment_entry):
    clear_sandbox_pe_run_link(payment_entry)
    frappe.delete_doc("Payment Entry", payment_entry, force=1, ignore_permissions=True, ignore_missing=True)
    return not bool(frappe.db.exists("Payment Entry", payment_entry))


def cancel_sales_invoice(sales_invoice):
    doc = frappe.get_doc("Sales Invoice", sales_invoice)
    doc.flags.ignore_permissions = True
    doc.cancel()
    doc.reload()
    return doc


def cleanup_scope(cleanup_payment_entries, cancel_submitted_invoices):
    if cleanup_payment_entries and cancel_submitted_invoices:
        return "Payment Entry Drafts + Submitted Sandbox Invoices"
    if cleanup_payment_entries:
        return "Payment Entry Drafts Only"
    if cancel_submitted_invoices:
        return "Submitted Sandbox Invoices Only"
    return "Payment Entry Drafts + Submitted Sandbox Invoices"


@frappe.whitelist()
def run_sandbox_accounting_cleanup_pack(
    target_payment_entry=None,
    target_sales_invoice=None,
    cleanup_payment_entries=1,
    cancel_submitted_invoices=1,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_sandbox_accounting_cleanup_pack")
    cleanup_payment_entries = int(cleanup_payment_entries or 0)
    cancel_submitted_invoices = int(cancel_submitted_invoices or 0)
    scope = cleanup_scope(cleanup_payment_entries, cancel_submitted_invoices)
    sandbox_config = validate_sandbox_config()
    errors = list(sandbox_config["errors"])
    warnings = []

    if not int(dry_run or 0) and acknowledgement != CLEANUP_ACK:
        errors.append(f"Invalid acknowledgement. Required: {CLEANUP_ACK}")

    pe_candidates = [evaluate_payment_entry_candidate(row) for row in find_payment_entry_candidates(target_payment_entry)] if cleanup_payment_entries else []
    si_candidates = [evaluate_sales_invoice_candidate(row) for row in find_sales_invoice_candidates(target_sales_invoice)] if cancel_submitted_invoices else []

    if cleanup_payment_entries and target_payment_entry and not pe_candidates:
        errors.append(f"Target Payment Entry not found as eligible sandbox draft candidate: {target_payment_entry}")
    if cancel_submitted_invoices and target_sales_invoice and not si_candidates:
        errors.append(f"Target Sales Invoice not found as submitted tagged sandbox candidate: {target_sales_invoice}")

    blocked_pe = [row for row in pe_candidates if not row["eligible"]]
    blocked_si = [row for row in si_candidates if not row["eligible"]]
    if blocked_pe:
        errors.append(f"{len(blocked_pe)} Payment Entry candidate(s) blocked.")
    if blocked_si:
        errors.append(f"{len(blocked_si)} Sales Invoice candidate(s) blocked.")

    validation = {
        "dry_run": bool(int(dry_run or 0)),
        "cleanup_scope": scope,
        "cleanup_payment_entries": cleanup_payment_entries,
        "cancel_submitted_invoices": cancel_submitted_invoices,
        "target_payment_entry": target_payment_entry,
        "target_sales_invoice": target_sales_invoice,
        "sandbox_config": sandbox_config,
        "errors": errors,
        "warnings": warnings,
        "required_acknowledgement": CLEANUP_ACK,
        "payment_entry_candidates": pe_candidates,
        "sales_invoice_candidates": si_candidates,
        "note": "Dry-run only. No Payment Entry deleted and no Sales Invoice cancelled." if int(dry_run or 0) else "Sandbox accounting cleanup requested.",
    }

    if int(dry_run or 0):
        return {
            **validation,
            "candidate_payment_entry_count": len(pe_candidates),
            "eligible_payment_entry_count": len([row for row in pe_candidates if row["eligible"]]),
            "candidate_sales_invoice_count": len(si_candidates),
            "eligible_sales_invoice_count": len([row for row in si_candidates if row["eligible"]]),
        }

    pack = create_pack(
        status="Blocked" if errors else "Previewed",
        cleanup_scope=scope,
        target_payment_entry=target_payment_entry,
        target_sales_invoice=target_sales_invoice,
        cleanup_payment_entries=cleanup_payment_entries,
        cancel_submitted_invoices=cancel_submitted_invoices,
        acknowledgement=acknowledgement,
        validation=validation,
        notes=notes,
    )

    deleted_pe_count = 0
    cancelled_si_count = 0

    if errors:
        for row in pe_candidates:
            add_line(pack, "Blocked" if not row["eligible"] else "Candidate", "Critical" if not row["eligible"] else "Low", "Delete Draft Sandbox Payment Entry", row, 1, "Blocked from deletion." if not row["eligible"] else "Candidate only; pack blocked.")
        for row in si_candidates:
            add_line(pack, "Blocked" if not row["eligible"] else "Candidate", "Critical" if not row["eligible"] else "Low", "Cancel Submitted Sandbox Sales Invoice", row, 1, "Blocked from cancellation." if not row["eligible"] else "Candidate only; pack blocked.")
        update_pack_summary(pack, pe_candidates, si_candidates, deleted_pe_count, cancelled_si_count)
        frappe.db.commit()
        return {**validation, "created": True, "cleanup_pack": pack.name, "pack_id": pack.pack_id, "status": "Blocked", "deleted_payment_entry_count": 0, "cancelled_sales_invoice_count": 0}

    for row in pe_candidates:
        deleted = delete_payment_entry(row["record_name"]) if row["eligible"] else False
        deleted_pe_count += 1 if deleted else 0
        row["linked_gl_after"] = gl_count("Payment Entry", row["record_name"])
        add_line(
            pack,
            "Deleted" if deleted else "Blocked",
            "Low" if deleted else "Critical",
            "Delete Draft Sandbox Payment Entry",
            row,
            1 if frappe.db.exists("Payment Entry", row["record_name"]) else 0,
            "Deleted draft tagged sandbox Payment Entry." if deleted else "Deletion failed.",
            None if deleted else "Payment Entry deletion failed.",
        )

    for row in si_candidates:
        cancelled = False
        block_reason = None
        if row["eligible"]:
            try:
                doc = cancel_sales_invoice(row["record_name"])
                cancelled = int(doc.docstatus or 0) == 2
                cancelled_si_count += 1 if cancelled else 0
                row["docstatus_after"] = int(doc.docstatus or 0)
            except Exception as exc:
                block_reason = str(exc)
        row["linked_gl_after"] = gl_count("Sales Invoice", row["record_name"])
        row["gl_net_after"] = gl_net("Sales Invoice", row["record_name"])
        add_line(
            pack,
            "Cancelled" if cancelled else "Blocked",
            "Low" if cancelled else "Critical",
            "Cancel Submitted Sandbox Sales Invoice",
            row,
            1 if frappe.db.exists("Sales Invoice", row["record_name"]) else 0,
            "Cancelled submitted tagged sandbox Sales Invoice through ERPNext workflow." if cancelled else "Cancellation failed.",
            block_reason,
        )

    update_pack_summary(pack, pe_candidates, si_candidates, deleted_pe_count, cancelled_si_count)
    guardrails = collect_post_guardrails()
    final_status = "Blocked" if guardrails["submitted_sandbox_pe_count"] or guardrails["payment_entry_gl_count_today"] or guardrails["submitted_payment_entry_count_today"] else "Cleaned"
    frappe.db.set_value(CLEANUP_PACK_DOCTYPE, pack.name, {"status": final_status, **guardrails}, update_modified=False)
    frappe.db.commit()

    return {
        **validation,
        "created": True,
        "cleanup_pack": pack.name,
        "pack_id": pack.pack_id,
        "status": final_status,
        "deleted_payment_entry_count": deleted_pe_count,
        "cancelled_sales_invoice_count": cancelled_si_count,
        "guardrails": guardrails,
        "note": "Cleanup pack completed. Draft sandbox Payment Entries were deleted. Submitted sandbox Sales Invoices were cancelled through ERPNext workflow only.",
    }


def update_pack_summary(pack, pe_candidates, si_candidates, deleted_pe_count, cancelled_si_count):
    sales_invoice_names = [row["record_name"] for row in si_candidates]
    guardrails = collect_post_guardrails()
    frappe.db.set_value(
        CLEANUP_PACK_DOCTYPE,
        pack.name,
        {
            "candidate_payment_entry_count": len(pe_candidates),
            "deleted_payment_entry_count": deleted_pe_count,
            "blocked_payment_entry_count": len([row for row in pe_candidates if not row["eligible"]]),
            "candidate_sales_invoice_count": len(si_candidates),
            "cancelled_sales_invoice_count": cancelled_si_count,
            "blocked_sales_invoice_count": len([row for row in si_candidates if not row["eligible"]]),
            "payment_entry_gl_count": sum(gl_count("Payment Entry", row["record_name"]) for row in pe_candidates),
            "sales_invoice_gl_count_before": sum(int(row["linked_gl_before"] or 0) for row in si_candidates),
            "sales_invoice_gl_count_after": sum(gl_count("Sales Invoice", name) for name in sales_invoice_names),
            "sandbox_si_gl_net_after": sum(gl_net("Sales Invoice", name) for name in sales_invoice_names),
            "blocker_count": frappe.db.count(CLEANUP_LINE_DOCTYPE, {"cleanup_pack": pack.name, "status": "Blocked"}),
            "warning_count": frappe.db.count(CLEANUP_LINE_DOCTYPE, {"cleanup_pack": pack.name, "status": "Warning"}),
            **guardrails,
        },
        update_modified=False,
    )


@frappe.whitelist()
def cancel_sandbox_accounting_cleanup_pack(cleanup_pack, reason=None):
    assert_action("cancel_sandbox_accounting_cleanup_pack")
    if not frappe.db.exists(CLEANUP_PACK_DOCTYPE, cleanup_pack):
        frappe.throw(_("Sandbox Accounting Cleanup Pack not found: {0}").format(cleanup_pack))
    frappe.db.set_value(
        CLEANUP_PACK_DOCTYPE,
        cleanup_pack,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "validation_log": reason or "Sandbox accounting cleanup pack cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{CLEANUP_LINE_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE cleanup_pack = %(cleanup_pack)s
        AND status NOT IN ('Deleted', 'Cancelled')
        """,
        {"cleanup_pack": cleanup_pack},
    )
    frappe.db.commit()
    return {"cleanup_pack": cleanup_pack, "status": "Cancelled", "note": "Cleanup pack cancelled as audit state only. Already deleted draft PEs and cancelled Sales Invoices are not recreated."}


@frappe.whitelist()
def quick_sandbox_accounting_cleanup_summary(limit=20):
    packs = frappe.get_all(
        CLEANUP_PACK_DOCTYPE,
        fields=[
            "name",
            "pack_id",
            "status",
            "cleanup_scope",
            "candidate_payment_entry_count",
            "deleted_payment_entry_count",
            "candidate_sales_invoice_count",
            "cancelled_sales_invoice_count",
            "payment_entry_gl_count_today",
            "submitted_payment_entry_count_today",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "sandbox_si_gl_net_after",
            "created_on",
            "created_by_user",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        CLEANUP_LINE_DOCTYPE,
        fields=[
            "name",
            "cleanup_pack",
            "status",
            "severity",
            "action_type",
            "record_doctype",
            "record_name",
            "docstatus_before",
            "docstatus_after",
            "linked_gl_count_before",
            "linked_gl_count_after",
            "gl_net_after",
            "amount",
            "action_taken",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "packs": packs,
        "lines": lines,
        "required_acknowledgement": CLEANUP_ACK,
        "guardrails": collect_post_guardrails(),
        "note": "Sandbox accounting cleanup summary only. Submitted sandbox Sales Invoices are cancelled through ERPNext workflow, never silently deleted.",
    }


def execute_cleanup_pack_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for field in ["status", "cleanup_scope"]:
        if filters.get(field):
            conditions.append(f"p.{field} = %({field})s")
            params[field] = filters.get(field)
    if filters.get("from_date"):
        conditions.append("DATE(p.created_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(p.created_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "cleanup_pack", "label": _("Cleanup Pack"), "fieldtype": "Link", "options": CLEANUP_PACK_DOCTYPE, "width": 220},
        {"fieldname": "pack_id", "label": _("Pack ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "cleanup_scope", "label": _("Scope"), "fieldtype": "Data", "width": 280},
        {"fieldname": "deleted_payment_entry_count", "label": _("Deleted PEs"), "fieldtype": "Int", "width": 100},
        {"fieldname": "cancelled_sales_invoice_count", "label": _("Cancelled SIs"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_today", "label": _("PE GL Today"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_payment_entry_count_today", "label": _("Submitted PE Today"), "fieldtype": "Int", "width": 140},
        {"fieldname": "sandbox_si_gl_net_after", "label": _("Sandbox SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS cleanup_pack, p.pack_id, p.status, p.cleanup_scope, p.deleted_payment_entry_count,
            p.cancelled_sales_invoice_count, p.payment_entry_gl_count_today, p.submitted_payment_entry_count_today,
            p.sandbox_si_gl_net_after, p.blocker_count, p.warning_count, p.created_on, %(currency)s AS currency
        FROM `tab{CLEANUP_PACK_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.pack_id for row in data[:20]], "datasets": [{"name": "Deleted PEs", "values": [int(row.deleted_payment_entry_count or 0) for row in data[:20]]}, {"name": "Cancelled SIs", "values": [int(row.cancelled_sales_invoice_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Cleanup Packs"), "datatype": "Int"},
        {"value": sum(int(row.deleted_payment_entry_count or 0) for row in data), "indicator": "Green", "label": _("Deleted PEs"), "datatype": "Int"},
        {"value": sum(int(row.cancelled_sales_invoice_count or 0) for row in data), "indicator": "Green", "label": _("Cancelled SIs"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_gl_count_today or 0) for row in data), "indicator": "Red", "label": _("PE GL Today"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_cleanup_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for field in ["cleanup_pack", "status", "record_doctype", "action_type"]:
        if filters.get(field):
            conditions.append(f"l.{field} = %({field})s")
            params[field] = filters.get(field)
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": CLEANUP_LINE_DOCTYPE, "width": 220},
        {"fieldname": "cleanup_pack", "label": _("Cleanup Pack"), "fieldtype": "Link", "options": CLEANUP_PACK_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "action_type", "label": _("Action"), "fieldtype": "Data", "width": 260},
        {"fieldname": "record_doctype", "label": _("Record Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "record_name", "label": _("Record Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "docstatus_before", "label": _("Before"), "fieldtype": "Int", "width": 80},
        {"fieldname": "docstatus_after", "label": _("After"), "fieldtype": "Int", "width": 80},
        {"fieldname": "linked_gl_count_before", "label": _("GL Before"), "fieldtype": "Int", "width": 90},
        {"fieldname": "linked_gl_count_after", "label": _("GL After"), "fieldtype": "Int", "width": 90},
        {"fieldname": "gl_net_after", "label": _("GL Net After"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "action_taken", "label": _("Action Taken"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.cleanup_pack, l.status, l.severity, l.action_type, l.record_doctype, l.record_name,
            l.docstatus_before, l.docstatus_after, l.linked_gl_count_before, l.linked_gl_count_after,
            l.gl_net_after, l.amount, l.action_taken, %(currency)s AS currency
        FROM `tab{CLEANUP_LINE_DOCTYPE}` l
        {build_where(conditions)}
        ORDER BY l.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Deleted"]), "indicator": "Green", "label": _("Deleted"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Cancelled"]), "indicator": "Green", "label": _("Cancelled"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_hygiene_report(filters=None):
    params = {"currency": currency()}
    columns = [
        {"fieldname": "record_type", "label": _("Record Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "record_name", "label": _("Record Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 90},
        {"fieldname": "status_label", "label": _("Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "linked_gl_count", "label": _("Linked GL Count"), "fieldtype": "Int", "width": 120},
        {"fieldname": "gl_net", "label": _("GL Net"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "hygiene_status", "label": _("Hygiene Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        """
        SELECT 'Payment Entry' AS record_type, pe.name AS record_name, pe.docstatus,
            CASE pe.docstatus WHEN 0 THEN 'Draft' WHEN 1 THEN 'Submitted' WHEN 2 THEN 'Cancelled' ELSE 'Unknown' END AS status_label,
            pe.paid_amount AS amount,
            (SELECT COUNT(*) FROM `tabGL Entry` gle WHERE gle.voucher_type='Payment Entry' AND gle.voucher_no=pe.name) AS linked_gl_count,
            (SELECT COALESCE(SUM(gle.debit - gle.credit), 0) FROM `tabGL Entry` gle WHERE gle.voucher_type='Payment Entry' AND gle.voucher_no=pe.name) AS gl_net,
            CASE WHEN pe.docstatus = 1 THEN 'Critical - Submitted Sandbox PE'
                 WHEN (SELECT COUNT(*) FROM `tabGL Entry` gle WHERE gle.voucher_type='Payment Entry' AND gle.voucher_no=pe.name) > 0 THEN 'Critical - PE GL Exists'
                 ELSE 'Draft Sandbox PE' END AS hygiene_status,
            %(currency)s AS currency
        FROM `tabPayment Entry` pe
        WHERE pe.custom_ndis_sandbox_payment_entry_draft_only = 1
        UNION ALL
        SELECT 'Sales Invoice' AS record_type, si.name AS record_name, si.docstatus,
            CASE si.docstatus WHEN 0 THEN 'Draft' WHEN 1 THEN 'Submitted' WHEN 2 THEN 'Cancelled' ELSE 'Unknown' END AS status_label,
            si.grand_total AS amount,
            (SELECT COUNT(*) FROM `tabGL Entry` gle WHERE gle.voucher_type='Sales Invoice' AND gle.voucher_no=si.name) AS linked_gl_count,
            (SELECT COALESCE(SUM(gle.debit - gle.credit), 0) FROM `tabGL Entry` gle WHERE gle.voucher_type='Sales Invoice' AND gle.voucher_no=si.name) AS gl_net,
            CASE WHEN si.docstatus = 2 THEN 'Clean - Cancelled Sandbox SI'
                 WHEN si.docstatus = 1 THEN 'Needs Cleanup - Submitted Sandbox SI'
                 WHEN si.docstatus = 0 THEN 'Info - Draft Sandbox SI'
                 ELSE 'Unknown' END AS hygiene_status,
            %(currency)s AS currency
        FROM `tabSales Invoice` si
        WHERE si.custom_ndis_sandbox_test_invoice = 1
        ORDER BY record_type, record_name
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.hygiene_status or "Unknown"] = chart_map.get(row.hygiene_status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Records", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Sandbox Records"), "datatype": "Int"},
        {"value": len([row for row in data if row.record_type == "Payment Entry" and row.docstatus == 1]), "indicator": "Red", "label": _("Submitted Sandbox PEs"), "datatype": "Int"},
        {"value": sum(int(row.linked_gl_count or 0) for row in data if row.record_type == "Payment Entry"), "indicator": "Red", "label": _("Payment Entry GL"), "datatype": "Int"},
        {"value": len([row for row in data if row.record_type == "Sales Invoice" and row.docstatus == 2]), "indicator": "Green", "label": _("Cancelled Sandbox SIs"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
