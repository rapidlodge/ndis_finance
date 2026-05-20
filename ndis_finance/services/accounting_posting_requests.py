import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from ndis_finance.services.permissions import assert_action


DRY_RUN_CONFIRMATION = "DRY_RUN_ONLY_NO_ACCOUNTING_POSTING"
HARD_BLOCK_MESSAGE = "Real accounting posting is blocked in Phase 2C."


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_request_id(event_type="Request"):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    safe_event = frappe.scrub(event_type or "Request").replace("_", "-").upper()
    return f"NDIS-ACC-REQUEST-{safe_event}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def get_preview(posting_preview):
    if not frappe.db.exists("NDIS Accounting Posting Preview", posting_preview):
        frappe.throw(_("NDIS Accounting Posting Preview not found: {0}").format(posting_preview))
    return frappe.get_doc("NDIS Accounting Posting Preview", posting_preview)


def get_policy(policy):
    if not frappe.db.exists("NDIS Accounting Posting Policy", policy):
        frappe.throw(_("NDIS Accounting Posting Policy not found: {0}").format(policy))
    return frappe.get_doc("NDIS Accounting Posting Policy", policy)


def get_open_request_for_preview(posting_preview):
    rows = frappe.get_all(
        "NDIS Accounting Posting Request",
        filters={
            "posting_preview": posting_preview,
            "status": ["not in", ["Cancelled", "Rejected", "Dry Run Failed"]],
        },
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


def validate_preview_for_request(preview, policy):
    items = []
    if preview.status == "Cancelled":
        items.append({"status": "Blocker", "label": "Preview cancelled", "detail": "Cancelled posting previews cannot be converted to posting requests."})
    if preview.validation_status == "Blocked" or int(preview.blocker_count or 0):
        items.append({"status": "Blocker", "label": "Preview has blockers", "detail": "Posting preview has blocker validation status."})
    if not int(preview.readiness_allowed or 0) and int(policy.requires_readiness_check or 0):
        items.append({"status": "Blocker", "label": "Readiness gate not allowed", "detail": "Policy requires production readiness and the preview does not have readiness_allowed enabled."})
    if not int(preview.governance_signed_off or 0) and int(policy.requires_governance_pack_signoff or 0):
        items.append({"status": "Blocker", "label": "Governance pack not signed off", "detail": "Policy requires signed governance pack and the preview does not have governance_signed_off enabled."})
    if policy.policy_status != "Active" or not int(policy.active or 0):
        items.append({"status": "Blocker", "label": "Policy inactive", "detail": "Posting policy is not active."})
    if policy.posting_mode == "Disabled":
        items.append({"status": "Blocker", "label": "Policy disabled", "detail": "Posting policy posting mode is Disabled."})
    if int(policy.allow_gl_entry or 0):
        items.append({"status": "Blocker", "label": "Direct GL Entry flag", "detail": "Policy allows GL Entry creation. Phase 2C blocks direct GL posting."})
    if preview.preview_only_confirmation != "PREVIEW_ONLY_NO_ACCOUNTING_POSTING":
        items.append({"status": "Warning", "label": "Preview-only confirmation not recognised", "detail": "Preview-only confirmation is not the expected Phase 2B value."})
    if int(preview.warning_count or 0):
        items.append({"status": "Warning", "label": "Preview warnings exist", "detail": f"Posting preview has {int(preview.warning_count or 0)} warning(s)."})
    return items


def get_preview_lines(posting_preview):
    return frappe.get_all(
        "NDIS Accounting Posting Preview Line",
        filters={"posting_preview": posting_preview, "status": ["!=", "Cancelled"]},
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


def request_line_status(preview_line_status):
    if preview_line_status == "Blocker":
        return "Blocker"
    if preview_line_status == "Warning":
        return "Warning"
    return "Ready"


def summarise_request_lines(lines):
    debit_total = sum(flt(row.amount) for row in lines if row.line_type == "Debit")
    credit_total = sum(flt(row.amount) for row in lines if row.line_type == "Credit")
    information_total = sum(flt(row.amount) for row in lines if row.line_type not in ["Debit", "Credit"])
    return {
        "debit_total": debit_total,
        "credit_total": credit_total,
        "request_total_amount": max(debit_total, credit_total, information_total),
        "blocker_count": len([row for row in lines if row.status == "Blocker"]),
        "warning_count": len([row for row in lines if row.status == "Warning"]),
        "variance_amount": debit_total - credit_total,
        "line_count": len(lines),
    }


def summarise_validation(validation_items, line_summary):
    blocker_count = len([row for row in validation_items if row["status"] == "Blocker"]) + int(line_summary.get("blocker_count") or 0)
    warning_count = len([row for row in validation_items if row["status"] == "Warning"]) + int(line_summary.get("warning_count") or 0)
    if blocker_count:
        return "Blocked", "Blocked", "Not Requested", blocker_count, warning_count
    if warning_count:
        return "Pending Approval", "Warning", "Pending", blocker_count, warning_count
    return "Pending Approval", "Pass", "Pending", blocker_count, warning_count


@frappe.whitelist()
def create_accounting_posting_request_from_preview(posting_preview, replace_existing=0, dry_run=0, notes=None):
    assert_action("create_accounting_posting_request")
    preview = get_preview(posting_preview)
    policy = get_policy(preview.policy)
    existing = get_open_request_for_preview(posting_preview)
    if existing and not int(replace_existing or 0):
        return {"created": False, "duplicate": True, "posting_request": existing, "message": "Open posting request already exists for this preview."}

    validation_items = validate_preview_for_request(preview, policy)
    copied_lines = []
    for row in get_preview_lines(posting_preview):
        copied_lines.append(
            frappe._dict(
                {
                    "posting_preview_line": row.name,
                    "status": request_line_status(row.status),
                    "line_no": row.line_no,
                    "line_label": row.line_label,
                    "line_type": row.line_type,
                    "target_entry_type": row.target_entry_type,
                    "account": row.account,
                    "cost_center": row.cost_center,
                    "party_type": row.party_type,
                    "party": row.party,
                    "amount": flt(row.amount),
                    "reference_doctype": row.reference_doctype,
                    "reference_name": row.reference_name,
                    "note": row.note,
                }
            )
        )
    if not copied_lines:
        validation_items.append({"status": "Blocker", "label": "No preview lines", "detail": "Posting preview has no active preview lines."})

    line_summary = summarise_request_lines(copied_lines)
    status, validation_status, approval_status, blocker_count, warning_count = summarise_validation(validation_items, line_summary)
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "posting_preview": posting_preview,
        "policy": policy.name,
        "event_type": preview.event_type,
        "source_doctype": preview.source_doctype,
        "source_name": preview.source_name,
        "status": status,
        "validation_status": validation_status,
        "approval_status": approval_status,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "line_summary": line_summary,
        "validation_items": validation_items,
        "request_lines": copied_lines,
        "hard_posting_block": 1,
        "real_posting_enabled": 0,
        "dry_run_confirmation": DRY_RUN_CONFIRMATION,
        "note": "Request conversion preview only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, or payment movement created.",
    }
    if int(dry_run or 0):
        return result
    if existing and int(replace_existing or 0):
        cancel_accounting_posting_request(existing, reason="Cancelled by replace_existing request creation.", ignore_permissions=True)

    doc = frappe.new_doc("NDIS Accounting Posting Request")
    doc.request_id = make_request_id(preview.event_type)
    doc.status = status
    doc.approval_status = approval_status
    doc.validation_status = validation_status
    doc.posting_preview = posting_preview
    doc.policy = policy.name
    doc.event_type = preview.event_type
    doc.source_doctype = preview.source_doctype
    doc.source_name = preview.source_name
    doc.source_summary = preview.source_summary
    doc.readiness_check = preview.readiness_check
    doc.readiness_allowed = int(preview.readiness_allowed or 0)
    doc.governance_pack = preview.governance_pack
    doc.governance_signed_off = int(preview.governance_signed_off or 0)
    doc.cfo_approval_required = int(preview.cfo_approval_required or 0)
    doc.hard_posting_block = 1
    doc.real_posting_enabled = 0
    doc.target_entry_type = preview.target_entry_type
    doc.posting_mode = preview.posting_mode
    doc.company = preview.company
    doc.posting_date = preview.posting_date
    doc.currency = preview.currency or currency()
    doc.request_total_amount = line_summary["request_total_amount"]
    doc.debit_total = line_summary["debit_total"]
    doc.credit_total = line_summary["credit_total"]
    doc.variance_amount = line_summary["variance_amount"]
    doc.line_count = line_summary["line_count"]
    doc.blocker_count = blocker_count
    doc.warning_count = warning_count
    doc.validation_log = safe_json(validation_items)
    doc.created_on = now_datetime()
    doc.created_by_user = frappe.session.user
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for row in copied_lines:
        line = frappe.new_doc("NDIS Accounting Posting Request Line")
        for fieldname in [
            "posting_preview_line",
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
        ]:
            setattr(line, fieldname, row.get(fieldname))
        line.posting_request = doc.name
        line.insert(ignore_permissions=True)

    frappe.db.commit()
    result.update({"created": True, "posting_request": doc.name, "request_id": doc.request_id})
    return result


@frappe.whitelist()
def approve_accounting_posting_request(posting_request, approval_note=None):
    assert_action("approve_accounting_posting_request")
    doc = frappe.get_doc("NDIS Accounting Posting Request", posting_request)
    if doc.status in ["Cancelled", "Rejected"]:
        frappe.throw(_("Cancelled or rejected posting requests cannot be approved."))
    if int(doc.blocker_count or 0):
        frappe.throw(_("Cannot approve posting request while blockers exist."))
    if not int(doc.readiness_allowed or 0):
        frappe.throw(_("Cannot approve posting request without production readiness allowed."))
    if not int(doc.governance_signed_off or 0):
        frappe.throw(_("Cannot approve posting request without signed governance pack."))
    if int(doc.real_posting_enabled or 0):
        frappe.throw(_("Real posting must remain disabled in Phase 2C."))
    if not int(doc.hard_posting_block or 0):
        frappe.throw(_("Hard posting block must remain enabled in Phase 2C."))
    frappe.db.set_value(
        "NDIS Accounting Posting Request",
        posting_request,
        {"status": "Approved", "approval_status": "Approved", "approved_by": frappe.session.user, "approved_on": now_datetime(), "approval_note": approval_note or "Approved for dry-run simulation only."},
        update_modified=False,
    )
    frappe.db.commit()
    return {"posting_request": posting_request, "status": "Approved", "approval_status": "Approved", "note": "Approved for dry-run simulation only. No accounting posting was enabled."}


@frappe.whitelist()
def reject_accounting_posting_request(posting_request, rejection_reason):
    assert_action("reject_accounting_posting_request")
    if not frappe.db.exists("NDIS Accounting Posting Request", posting_request):
        frappe.throw(_("Accounting Posting Request not found: {0}").format(posting_request))
    frappe.db.set_value(
        "NDIS Accounting Posting Request",
        posting_request,
        {"status": "Rejected", "approval_status": "Rejected", "rejected_by": frappe.session.user, "rejected_on": now_datetime(), "rejection_reason": rejection_reason},
        update_modified=False,
    )
    frappe.db.commit()
    return {"posting_request": posting_request, "status": "Rejected", "note": "Posting request rejected internally only. No accounting movement created."}


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


def simulate_posting(doc, lines):
    result = {
        "request": doc.name,
        "request_id": doc.request_id,
        "target_entry_type": doc.target_entry_type,
        "posting_mode": doc.posting_mode,
        "hard_posting_block": int(doc.hard_posting_block or 0),
        "real_posting_enabled": int(doc.real_posting_enabled or 0),
        "line_count": len(lines),
        "debit_total": sum(flt(row.amount) for row in lines if row.line_type == "Debit"),
        "credit_total": sum(flt(row.amount) for row in lines if row.line_type == "Credit"),
        "information_total": sum(flt(row.amount) for row in lines if row.line_type not in ["Debit", "Credit"]),
        "simulated_documents": [],
        "blockers": [],
        "warnings": [],
        "confirmation": DRY_RUN_CONFIRMATION,
        "posting_block_message": HARD_BLOCK_MESSAGE,
    }
    if not int(doc.hard_posting_block or 0):
        result["blockers"].append("Hard posting block is not enabled.")
    if int(doc.real_posting_enabled or 0):
        result["blockers"].append("Real posting enabled flag is unexpectedly on.")
    if doc.approval_status != "Approved":
        result["blockers"].append("Posting request is not CFO-approved.")
    if int(doc.blocker_count or 0):
        result["blockers"].append("Posting request has blocker count greater than zero.")
    if not lines:
        result["blockers"].append("No request lines found.")
    if doc.target_entry_type in ["Journal Entry", "Payment Entry"] and result["debit_total"] != result["credit_total"] and (result["debit_total"] or result["credit_total"]):
        result["warnings"].append("Debit and credit preview totals do not match. This remains dry-run only.")

    if doc.posting_mode == "Management Only":
        result["simulated_documents"].append({"target_entry_type": "None", "status": "Not Applicable", "message": "Management-only policy. No accounting document would be created."})
    elif doc.target_entry_type in ["Payment Entry", "Journal Entry", "Sales Invoice", "Purchase Invoice"]:
        result["simulated_documents"].append({"target_entry_type": doc.target_entry_type, "status": "Simulated Only", "message": f"{doc.target_entry_type} structure simulated. Creation is blocked in Phase 2C."})
    else:
        result["simulated_documents"].append({"target_entry_type": doc.target_entry_type or "None", "status": "Control Only", "message": "No target accounting entry type selected."})
    result["passed"] = not bool(result["blockers"])
    return result


@frappe.whitelist()
def dry_run_accounting_posting_request(posting_request):
    assert_action("dry_run_accounting_posting_request")
    doc = frappe.get_doc("NDIS Accounting Posting Request", posting_request)
    if doc.status not in ["Approved", "Dry Run Failed", "Dry Run Passed"]:
        frappe.throw(_("Posting request must be Approved before dry-run simulation."))
    lines = get_request_lines(posting_request)
    result = simulate_posting(doc, lines)
    new_status = "Dry Run Passed" if result["passed"] else "Dry Run Failed"
    for line in lines:
        frappe.db.set_value(
            "NDIS Accounting Posting Request Line",
            line.name,
            {"status": "Simulated" if result["passed"] and line.status == "Ready" else line.status, "simulation_status": "Simulated Only - No Accounting Posting"},
            update_modified=False,
        )
    frappe.db.set_value(
        "NDIS Accounting Posting Request",
        posting_request,
        {"status": new_status, "dry_run_on": now_datetime(), "dry_run_by": frappe.session.user, "dry_run_status": "Passed" if result["passed"] else "Failed", "dry_run_result_json": safe_json(result)},
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "posting_request": posting_request,
        "status": new_status,
        "dry_run_result": result,
        "note": "Dry-run simulation only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, bank allocation, or payment movement created.",
    }


@frappe.whitelist()
def cancel_accounting_posting_request(posting_request, reason=None, ignore_permissions=False):
    if not ignore_permissions:
        assert_action("cancel_accounting_posting_request")
    if not frappe.db.exists("NDIS Accounting Posting Request", posting_request):
        frappe.throw(_("Accounting Posting Request not found: {0}").format(posting_request))
    frappe.db.set_value(
        "NDIS Accounting Posting Request",
        posting_request,
        {"status": "Cancelled", "approval_status": "Not Requested", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "validation_log": reason or "Posting request cancelled."},
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Accounting Posting Request Line`
        SET status = 'Cancelled'
        WHERE posting_request = %(posting_request)s
        """,
        {"posting_request": posting_request},
    )
    frappe.db.commit()
    return {"posting_request": posting_request, "status": "Cancelled", "note": "Posting request cancelled only. No accounting/payroll/payment records were changed."}


@frappe.whitelist()
def blocked_real_accounting_posting_attempt(posting_request):
    frappe.throw(_("Real accounting posting is intentionally blocked in Phase 2C. Complete future sandbox-only phases before enabling any live posting."))


@frappe.whitelist()
def quick_accounting_posting_request_summary(limit=20):
    requests = frappe.get_all(
        "NDIS Accounting Posting Request",
        fields=[
            "name",
            "request_id",
            "status",
            "approval_status",
            "validation_status",
            "posting_preview",
            "policy",
            "event_type",
            "source_doctype",
            "source_name",
            "target_entry_type",
            "posting_mode",
            "request_total_amount",
            "line_count",
            "blocker_count",
            "warning_count",
            "readiness_allowed",
            "governance_signed_off",
            "hard_posting_block",
            "real_posting_enabled",
            "dry_run_status",
            "created_on",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Accounting Posting Request Line",
        fields=["name", "posting_request", "status", "line_no", "line_label", "line_type", "target_entry_type", "amount", "reference_doctype", "reference_name", "simulation_status"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "requests": requests,
        "lines": lines,
        "dry_run_confirmation": DRY_RUN_CONFIRMATION,
        "hard_block_message": HARD_BLOCK_MESSAGE,
        "note": "Accounting posting request summary only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, or payment movement created.",
    }


def execute_request_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["status", "approval_status", "validation_status", "event_type", "policy", "source_doctype"]:
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
        {"fieldname": "posting_request", "label": _("Posting Request"), "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "width": 220},
        {"fieldname": "request_id", "label": _("Request ID"), "fieldtype": "Data", "width": 310},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "approval_status", "label": _("Approval"), "fieldtype": "Data", "width": 110},
        {"fieldname": "validation_status", "label": _("Validation"), "fieldtype": "Data", "width": 110},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": "NDIS Accounting Posting Policy", "width": 220},
        {"fieldname": "posting_preview", "label": _("Preview"), "fieldtype": "Link", "options": "NDIS Accounting Posting Preview", "width": 220},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 190},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "target_entry_type", "label": _("Target Entry"), "fieldtype": "Data", "width": 130},
        {"fieldname": "posting_mode", "label": _("Posting Mode"), "fieldtype": "Data", "width": 160},
        {"fieldname": "request_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hard_posting_block", "label": _("Hard Block"), "fieldtype": "Check", "width": 100},
        {"fieldname": "real_posting_enabled", "label": _("Real Posting"), "fieldtype": "Check", "width": 100},
        {"fieldname": "dry_run_status", "label": _("Dry-run"), "fieldtype": "Data", "width": 100},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT r.name AS posting_request, r.request_id, r.status, r.approval_status, r.validation_status,
            r.event_type, r.policy, r.posting_preview, r.source_doctype, r.source_name, r.target_entry_type,
            r.posting_mode, r.request_total_amount, r.line_count, r.blocker_count, r.warning_count,
            r.hard_posting_block, r.real_posting_enabled, r.dry_run_status, r.created_on, %(currency)s AS currency
        FROM `tabNDIS Accounting Posting Request` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.request_id for row in data[:20]], "datasets": [{"name": "Amount", "values": [flt(row.request_total_amount) for row in data[:20]]}, {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]}, {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Requests"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Approved"]), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Dry Run Passed"]), "indicator": "Green", "label": _("Dry Run Passed"), "datatype": "Int"},
        {"value": len([row for row in data if row.status in ["Blocked", "Dry Run Failed"]]), "indicator": "Red", "label": _("Blocked/Failed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_request_line_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for fieldname in ["posting_request", "status", "line_type", "target_entry_type"]:
        if filters.get(fieldname):
            conditions.append(f"l.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "line", "label": _("Line"), "fieldtype": "Link", "options": "NDIS Accounting Posting Request Line", "width": 220},
        {"fieldname": "posting_request", "label": _("Posting Request"), "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "line_label", "label": _("Line Label"), "fieldtype": "Data", "width": 240},
        {"fieldname": "line_type", "label": _("Line Type"), "fieldtype": "Data", "width": 110},
        {"fieldname": "target_entry_type", "label": _("Target Entry"), "fieldtype": "Data", "width": 130},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 220},
        {"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Link", "options": "Cost Center", "width": 180},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "reference_doctype", "label": _("Reference DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "reference_name", "label": _("Reference Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "simulation_status", "label": _("Simulation Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT l.name AS line, l.posting_request, l.status, l.line_no, l.line_label, l.line_type,
            l.target_entry_type, l.account, l.cost_center, l.amount, l.reference_doctype,
            l.reference_name, l.simulation_status, l.note, %(currency)s AS currency
        FROM `tabNDIS Accounting Posting Request Line` l
        {build_where(conditions)}
        ORDER BY l.creation DESC, l.line_no ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.line_type or "Information"
        chart_map[key] = chart_map.get(key, 0) + flt(row.amount)
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Amount", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Lines"), "datatype": "Int"},
        {"value": sum(flt(row.amount) for row in data if row.line_type == "Debit"), "indicator": "Blue", "label": _("Debit Total"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.amount) for row in data if row.line_type == "Credit"), "indicator": "Green", "label": _("Credit Total"), "datatype": "Currency", "currency": currency()},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
