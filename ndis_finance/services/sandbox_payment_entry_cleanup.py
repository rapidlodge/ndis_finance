import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_datetime, getdate, now_datetime, today

from ndis_finance.services.permissions import assert_action


CLEANUP_ACK = "I_CONFIRM_DELETE_NDIS_SANDBOX_DRAFT_PAYMENT_ENTRY_ONLY"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_cleanup_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-PE-CLEANUP-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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

    return {
        "sandbox_enabled": sandbox_enabled,
        "production_mode": production_mode,
        "errors": errors,
    }


def get_gl_count_for_payment_entry(payment_entry):
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0

    return frappe.db.count(
        "GL Entry",
        {
            "voucher_type": "Payment Entry",
            "voucher_no": payment_entry,
        },
    )


def find_candidates(target_sandbox_run=None, target_payment_entry=None, older_than_days=0, include_cancelled_runs=1):
    conditions = ["pe.custom_ndis_sandbox_payment_entry_draft_only = 1"]
    params = {}

    if target_payment_entry:
        conditions.append("pe.name = %(target_payment_entry)s")
        params["target_payment_entry"] = target_payment_entry

    if target_sandbox_run:
        conditions.append("pe.custom_ndis_sandbox_payment_entry_run = %(target_sandbox_run)s")
        params["target_sandbox_run"] = target_sandbox_run

    if int(older_than_days or 0) > 0:
        conditions.append("DATE(pe.creation) <= DATE_SUB(CURDATE(), INTERVAL %(older_than_days)s DAY)")
        params["older_than_days"] = int(older_than_days)

    if not int(include_cancelled_runs or 0):
        conditions.append(
            """
            (
                pe.custom_ndis_sandbox_payment_entry_run IS NULL
                OR pe.custom_ndis_sandbox_payment_entry_run = ''
                OR EXISTS (
                    SELECT 1
                    FROM `tabNDIS Sandbox Payment Entry Run` sr
                    WHERE sr.name = pe.custom_ndis_sandbox_payment_entry_run
                    AND sr.status != 'Cancelled'
                )
            )
            """
        )

    return frappe.db.sql(
        f"""
        SELECT
            pe.name,
            pe.docstatus,
            pe.company,
            pe.posting_date,
            pe.creation,
            pe.party,
            pe.paid_amount,
            pe.received_amount,
            pe.custom_ndis_sandbox_payment_entry_draft_only,
            pe.custom_ndis_sandbox_payment_entry_run,
            pe.custom_ndis_payment_entry_allocation_preview,
            pe.custom_ndis_sandbox_payment_entry_acknowledgement
        FROM `tabPayment Entry` pe
        WHERE {" AND ".join(conditions)}
        ORDER BY pe.creation ASC
        """,
        params,
        as_dict=True,
    )


def validate_candidate(row):
    reasons = []

    gl_count = get_gl_count_for_payment_entry(row.name)
    age_days = date_diff(today(), getdate(row.creation))

    if not frappe.db.exists("Payment Entry", row.name):
        reasons.append("Payment Entry no longer exists.")

    if int(row.docstatus or 0) != 0:
        reasons.append("Payment Entry is not draft docstatus 0.")

    if not int(row.custom_ndis_sandbox_payment_entry_draft_only or 0):
        reasons.append("Payment Entry is not tagged as NDIS sandbox draft only.")

    if gl_count:
        reasons.append(f"Linked GL Entry exists: {gl_count}.")

    if not row.custom_ndis_sandbox_payment_entry_run:
        reasons.append("Missing linked NDIS sandbox Payment Entry run.")

    return {
        "payment_entry": row.name,
        "sandbox_run": row.custom_ndis_sandbox_payment_entry_run,
        "allocation_preview": row.custom_ndis_payment_entry_allocation_preview,
        "party": row.party,
        "company": row.company,
        "posting_date": row.posting_date,
        "docstatus": int(row.docstatus or 0),
        "sandbox_draft_only": int(row.custom_ndis_sandbox_payment_entry_draft_only or 0),
        "linked_gl_entry_count": gl_count,
        "age_days": age_days,
        "paid_amount": flt(row.paid_amount),
        "received_amount": flt(row.received_amount),
        "eligible": not bool(reasons),
        "block_reason": "; ".join(reasons),
    }


def clear_links_before_delete(candidate):
    sandbox_run = candidate.get("sandbox_run")
    payment_entry = candidate.get("payment_entry")

    if sandbox_run and frappe.db.exists("NDIS Sandbox Payment Entry Run", sandbox_run):
        frappe.db.set_value(
            "NDIS Sandbox Payment Entry Run",
            sandbox_run,
            {
                "payment_entry": None,
                "payment_entry_docstatus": 0,
                "validation_log": f"Sandbox draft Payment Entry {payment_entry} deleted by Phase 3D cleanup.",
            },
            update_modified=False,
        )


def delete_candidate_payment_entry(candidate):
    payment_entry = candidate.get("payment_entry")

    if not payment_entry:
        return False

    clear_links_before_delete(candidate)

    frappe.delete_doc(
        "Payment Entry",
        payment_entry,
        force=1,
        ignore_permissions=True,
        ignore_missing=True,
    )

    return not bool(frappe.db.exists("Payment Entry", payment_entry))


@frappe.whitelist()
def run_sandbox_payment_entry_cleanup(
    target_sandbox_run=None,
    target_payment_entry=None,
    older_than_days=0,
    include_cancelled_runs=1,
    delete_payment_entries=0,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_sandbox_payment_entry_cleanup")

    sandbox_config = validate_sandbox_config()

    candidates_raw = find_candidates(
        target_sandbox_run=target_sandbox_run,
        target_payment_entry=target_payment_entry,
        older_than_days=older_than_days,
        include_cancelled_runs=include_cancelled_runs,
    )

    candidates = [validate_candidate(row) for row in candidates_raw]

    eligible = [row for row in candidates if row["eligible"]]
    blocked = [row for row in candidates if not row["eligible"]]

    submitted_sandbox_pe_count = frappe.db.count(
        "Payment Entry",
        {
            "custom_ndis_sandbox_payment_entry_draft_only": 1,
            "docstatus": 1,
        },
    )

    linked_gl_entry_count = sum(int(row["linked_gl_entry_count"] or 0) for row in candidates)

    errors = list(sandbox_config["errors"])

    if int(delete_payment_entries or 0):
        if acknowledgement != CLEANUP_ACK:
            errors.append(f"Invalid acknowledgement. Required: {CLEANUP_ACK}")

        if submitted_sandbox_pe_count:
            errors.append(f"Submitted sandbox Payment Entries exist: {submitted_sandbox_pe_count}.")

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "delete_payment_entries": int(delete_payment_entries or 0),
        "required_acknowledgement": CLEANUP_ACK,
        "acknowledgement_ok": acknowledgement == CLEANUP_ACK,
        "sandbox_config": sandbox_config,
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "deleted_payment_entry_count": 0,
        "submitted_sandbox_pe_count": submitted_sandbox_pe_count,
        "linked_gl_entry_count": linked_gl_entry_count,
        "errors": errors,
        "candidates": candidates,
        "note": "Cleanup preview only. No Payment Entry deleted." if int(dry_run or 0) else "Sandbox Payment Entry cleanup requested.",
    }

    if int(dry_run or 0):
        return result

    cleanup_status = "Blocked" if errors else "Previewed"
    cleanup_mode = "Delete Draft Sandbox Payment Entry" if int(delete_payment_entries or 0) else "Preview Only"

    run = create_cleanup_run_record(
        status=cleanup_status,
        cleanup_mode=cleanup_mode,
        target_sandbox_run=target_sandbox_run,
        target_payment_entry=target_payment_entry,
        older_than_days=older_than_days,
        include_cancelled_runs=include_cancelled_runs,
        acknowledgement=acknowledgement,
        candidates=candidates,
        validation_log=result,
        notes=notes,
    )

    deleted_count = 0

    if not errors and int(delete_payment_entries or 0):
        for candidate in eligible:
            deleted = delete_candidate_payment_entry(candidate)
            deleted_count += 1 if deleted else 0

            frappe.db.sql(
                """
                UPDATE `tabNDIS Sandbox Payment Entry Cleanup Line`
                SET
                    status = %(status)s,
                    payment_entry_exists_after = %(exists_after)s,
                    action_taken = %(action_taken)s
                WHERE cleanup_run = %(cleanup_run)s
                AND payment_entry = %(payment_entry)s
                """,
                {
                    "status": "Deleted" if deleted else "Blocked",
                    "exists_after": 0 if deleted else 1,
                    "action_taken": "Draft sandbox Payment Entry deleted." if deleted else "Deletion failed or Payment Entry still exists.",
                    "cleanup_run": run.name,
                    "payment_entry": candidate["payment_entry"],
                },
            )

        frappe.db.set_value(
            "NDIS Sandbox Payment Entry Cleanup Run",
            run.name,
            {
                "status": "Cleaned",
                "deleted_payment_entry_count": deleted_count,
            },
            update_modified=False,
        )

    frappe.db.commit()

    result["created"] = True
    result["cleanup_run"] = run.name
    result["cleanup_id"] = run.cleanup_id
    result["deleted_payment_entry_count"] = deleted_count
    result["status"] = "Cleaned" if deleted_count else cleanup_status

    return result


def create_cleanup_run_record(
    status,
    cleanup_mode,
    target_sandbox_run,
    target_payment_entry,
    older_than_days,
    include_cancelled_runs,
    acknowledgement,
    candidates,
    validation_log,
    notes=None,
):
    run = frappe.new_doc("NDIS Sandbox Payment Entry Cleanup Run")
    run.cleanup_id = make_cleanup_id()
    run.status = status
    run.cleanup_mode = cleanup_mode
    run.target_sandbox_run = target_sandbox_run
    run.target_payment_entry = target_payment_entry
    run.older_than_days = int(older_than_days or 0)
    run.include_cancelled_runs = int(include_cancelled_runs or 0)
    run.site_name = frappe.local.site
    run.sandbox_config_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    run.production_mode_detected = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    run.required_acknowledgement = CLEANUP_ACK
    run.acknowledgement = acknowledgement
    run.candidate_count = len(candidates)
    run.eligible_count = len([row for row in candidates if row["eligible"]])
    run.blocked_count = len([row for row in candidates if not row["eligible"]])
    run.deleted_payment_entry_count = 0
    run.linked_gl_entry_count = sum(int(row["linked_gl_entry_count"] or 0) for row in candidates)
    run.submitted_sandbox_pe_count = frappe.db.count(
        "Payment Entry",
        {
            "custom_ndis_sandbox_payment_entry_draft_only": 1,
            "docstatus": 1,
        },
    )
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation_log)
    run.notes = notes
    run.insert(ignore_permissions=True)

    for idx, candidate in enumerate(candidates, start=1):
        line = frappe.new_doc("NDIS Sandbox Payment Entry Cleanup Line")
        line.cleanup_run = run.name
        line.status = "Eligible" if candidate["eligible"] else "Blocked"
        line.line_no = idx
        line.sandbox_run = candidate["sandbox_run"]
        line.payment_entry = candidate["payment_entry"]
        line.payment_entry_exists_before = 1
        line.payment_entry_exists_after = 1
        line.payment_entry_docstatus = candidate["docstatus"]
        line.sandbox_draft_only = candidate["sandbox_draft_only"]
        line.linked_gl_entry_count = candidate["linked_gl_entry_count"]
        line.age_days = candidate["age_days"]
        line.allocation_preview = candidate["allocation_preview"]
        line.party = candidate["party"]
        line.company = candidate["company"]
        line.posting_date = candidate["posting_date"]
        line.paid_amount = candidate["paid_amount"]
        line.received_amount = candidate["received_amount"]
        line.block_reason = candidate["block_reason"]
        line.action_taken = "Eligible for deletion." if candidate["eligible"] else "Blocked from deletion."
        line.insert(ignore_permissions=True)

    return run


@frappe.whitelist()
def cancel_sandbox_payment_entry_cleanup(cleanup_run, reason=None):
    assert_action("cancel_sandbox_payment_entry_cleanup")

    if not frappe.db.exists("NDIS Sandbox Payment Entry Cleanup Run", cleanup_run):
        frappe.throw(_("Sandbox Payment Entry Cleanup Run not found: {0}").format(cleanup_run))

    frappe.db.set_value(
        "NDIS Sandbox Payment Entry Cleanup Run",
        cleanup_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "validation_log": reason or "Sandbox Payment Entry cleanup run cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Sandbox Payment Entry Cleanup Line`
        SET status = 'Cancelled'
        WHERE cleanup_run = %(cleanup_run)s
        AND status NOT IN ('Deleted')
        """,
        {"cleanup_run": cleanup_run},
    )

    frappe.db.commit()

    return {
        "cleanup_run": cleanup_run,
        "status": "Cancelled",
        "note": "Cleanup run cancelled. Already-deleted draft sandbox Payment Entries are not recreated.",
    }


@frappe.whitelist()
def quick_sandbox_payment_entry_cleanup_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Sandbox Payment Entry Cleanup Run",
        fields=[
            "name",
            "cleanup_id",
            "status",
            "cleanup_mode",
            "candidate_count",
            "eligible_count",
            "blocked_count",
            "deleted_payment_entry_count",
            "linked_gl_entry_count",
            "submitted_sandbox_pe_count",
            "created_on",
            "created_by_user",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    lines = frappe.get_all(
        "NDIS Sandbox Payment Entry Cleanup Line",
        fields=[
            "name",
            "cleanup_run",
            "status",
            "sandbox_run",
            "payment_entry",
            "payment_entry_exists_before",
            "payment_entry_exists_after",
            "payment_entry_docstatus",
            "sandbox_draft_only",
            "linked_gl_entry_count",
            "age_days",
            "action_taken",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    guardrails = {
        "draft_sandbox_payment_entries": frappe.db.count(
            "Payment Entry",
            {
                "custom_ndis_sandbox_payment_entry_draft_only": 1,
                "docstatus": 0,
            },
        ),
        "submitted_sandbox_payment_entries": frappe.db.count(
            "Payment Entry",
            {
                "custom_ndis_sandbox_payment_entry_draft_only": 1,
                "docstatus": 1,
            },
        ),
        "submitted_payment_entries_today": frappe.db.count(
            "Payment Entry",
            {
                "creation": [">=", today()],
                "docstatus": 1,
            },
        ),
        "gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
    }

    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement": CLEANUP_ACK,
        "note": "Sandbox Payment Entry cleanup summary only. Cleanup can delete draft tagged sandbox Payment Entries only. It cannot delete submitted Payment Entries or any Payment Entry with GL Entries.",
    }


def execute_cleanup_report(filters=None):
    filters = frappe._dict(filters or {})

    conditions = []
    params = {}

    status = filters.get("status")
    cleanup_mode = filters.get("cleanup_mode")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if status:
        conditions.append("r.status = %(status)s")
        params["status"] = status

    if cleanup_mode:
        conditions.append("r.cleanup_mode = %(cleanup_mode)s")
        params["cleanup_mode"] = cleanup_mode

    if from_date:
        conditions.append("DATE(r.created_on) >= %(from_date)s")
        params["from_date"] = from_date

    if to_date:
        conditions.append("DATE(r.created_on) <= %(to_date)s")
        params["to_date"] = to_date

    columns = [
        {"fieldname": "cleanup_run", "label": _("Cleanup Run"), "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Cleanup Run", "width": 220},
        {"fieldname": "cleanup_id", "label": _("Cleanup ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "cleanup_mode", "label": _("Cleanup Mode"), "fieldtype": "Data", "width": 230},
        {"fieldname": "candidate_count", "label": _("Candidates"), "fieldtype": "Int", "width": 100},
        {"fieldname": "eligible_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "deleted_payment_entry_count", "label": _("Deleted PEs"), "fieldtype": "Int", "width": 110},
        {"fieldname": "linked_gl_entry_count", "label": _("Linked GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "submitted_sandbox_pe_count", "label": _("Submitted Sandbox PEs"), "fieldtype": "Int", "width": 160},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "created_by_user", "label": _("Created By"), "fieldtype": "Link", "options": "User", "width": 160},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS cleanup_run,
            r.cleanup_id,
            r.status,
            r.cleanup_mode,
            r.candidate_count,
            r.eligible_count,
            r.blocked_count,
            r.deleted_payment_entry_count,
            r.linked_gl_entry_count,
            r.submitted_sandbox_pe_count,
            r.created_on,
            r.created_by_user
        FROM `tabNDIS Sandbox Payment Entry Cleanup Run` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.cleanup_id for row in data[:20]],
            "datasets": [
                {"name": "Eligible", "values": [int(row.eligible_count or 0) for row in data[:20]]},
                {"name": "Deleted", "values": [int(row.deleted_payment_entry_count or 0) for row in data[:20]]},
                {"name": "Blocked", "values": [int(row.blocked_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Cleanup Runs"), "datatype": "Int"},
        {"value": sum(int(row.deleted_payment_entry_count or 0) for row in data), "indicator": "Green", "label": _("Deleted Draft PEs"), "datatype": "Int"},
        {"value": sum(int(row.blocked_count or 0) for row in data), "indicator": "Red", "label": _("Blocked Lines"), "datatype": "Int"},
        {"value": sum(int(row.submitted_sandbox_pe_count or 0) for row in data), "indicator": "Red", "label": _("Submitted Sandbox PEs"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_hygiene_report(filters=None):
    filters = frappe._dict(filters or {})

    conditions = ["pe.custom_ndis_sandbox_payment_entry_draft_only = 1"]
    params = {}

    docstatus = filters.get("docstatus")
    sandbox_run = filters.get("sandbox_run")
    min_age_days = filters.get("min_age_days")

    if docstatus not in [None, ""]:
        conditions.append("pe.docstatus = %(docstatus)s")
        params["docstatus"] = int(docstatus)

    if sandbox_run:
        conditions.append("pe.custom_ndis_sandbox_payment_entry_run = %(sandbox_run)s")
        params["sandbox_run"] = sandbox_run

    if min_age_days not in [None, ""]:
        conditions.append("DATE(pe.creation) <= DATE_SUB(CURDATE(), INTERVAL %(min_age_days)s DAY)")
        params["min_age_days"] = int(min_age_days)

    params["currency"] = currency()

    columns = [
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 190},
        {"fieldname": "docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 90},
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run", "width": 220},
        {"fieldname": "allocation_preview", "label": _("Allocation Preview"), "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 180},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "age_days", "label": _("Age Days"), "fieldtype": "Int", "width": 90},
        {"fieldname": "paid_amount", "label": _("Paid Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "received_amount", "label": _("Received Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "gl_count", "label": _("GL Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hygiene_status", "label": _("Hygiene Status"), "fieldtype": "Data", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            pe.name AS payment_entry,
            pe.docstatus,
            pe.custom_ndis_sandbox_payment_entry_run AS sandbox_run,
            pe.custom_ndis_payment_entry_allocation_preview AS allocation_preview,
            pe.company,
            pe.party,
            pe.posting_date,
            DATEDIFF(CURDATE(), DATE(pe.creation)) AS age_days,
            pe.paid_amount,
            pe.received_amount,
            (
                SELECT COUNT(*)
                FROM `tabGL Entry` gle
                WHERE gle.voucher_type = 'Payment Entry'
                AND gle.voucher_no = pe.name
            ) AS gl_count,
            CASE
                WHEN pe.docstatus = 1 THEN 'Submitted - Critical'
                WHEN (
                    SELECT COUNT(*)
                    FROM `tabGL Entry` gle
                    WHERE gle.voucher_type = 'Payment Entry'
                    AND gle.voucher_no = pe.name
                ) > 0 THEN 'GL Exists - Critical'
                WHEN DATEDIFF(CURDATE(), DATE(pe.creation)) >= 7 THEN 'Old Draft'
                ELSE 'Draft OK'
            END AS hygiene_status,
            %(currency)s AS currency
        FROM `tabPayment Entry` pe
        WHERE {" AND ".join(conditions)}
        ORDER BY pe.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in data:
        key = row.hygiene_status or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Payment Entries", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Sandbox PEs"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 0]), "indicator": "Green", "label": _("Draft"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 1]), "indicator": "Red", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(int(row.gl_count or 0) for row in data), "indicator": "Red", "label": _("Linked GL Entries"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
