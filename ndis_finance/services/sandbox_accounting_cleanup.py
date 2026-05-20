import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_datetime, getdate, now_datetime, today

from ndis_finance.services.permissions import assert_action


CLEANUP_ACK = "I_CONFIRM_DELETE_NDIS_SANDBOX_DRAFT_JE_ONLY"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_cleanup_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SANDBOX-CLEANUP-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_gl_count_for_je(journal_entry):
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0
    return frappe.db.count("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": journal_entry})


def get_je_totals(journal_entry):
    rows = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(debit_in_account_currency), 0) AS debit_total,
            COALESCE(SUM(credit_in_account_currency), 0) AS credit_total
        FROM `tabJournal Entry Account`
        WHERE parent = %(journal_entry)s
        """,
        {"journal_entry": journal_entry},
        as_dict=True,
    )
    if not rows:
        return 0, 0
    return flt(rows[0].debit_total), flt(rows[0].credit_total)


def find_candidates(target_sandbox_run=None, target_journal_entry=None, older_than_days=0, include_cancelled_runs=1):
    conditions = ["je.custom_ndis_sandbox_draft_only = 1"]
    params = {}
    if target_journal_entry:
        conditions.append("je.name = %(target_journal_entry)s")
        params["target_journal_entry"] = target_journal_entry
    if target_sandbox_run:
        conditions.append("je.custom_ndis_sandbox_posting_run = %(target_sandbox_run)s")
        params["target_sandbox_run"] = target_sandbox_run
    if int(older_than_days or 0) > 0:
        conditions.append("DATE(je.creation) <= DATE_SUB(CURDATE(), INTERVAL %(older_than_days)s DAY)")
        params["older_than_days"] = int(older_than_days)
    if not int(include_cancelled_runs or 0):
        conditions.append(
            """
            (
                je.custom_ndis_sandbox_posting_run IS NULL
                OR je.custom_ndis_sandbox_posting_run = ''
                OR EXISTS (
                    SELECT 1
                    FROM `tabNDIS Sandbox Accounting Posting Run` sr
                    WHERE sr.name = je.custom_ndis_sandbox_posting_run
                    AND sr.status != 'Cancelled'
                )
            )
            """
        )

    rows = frappe.db.sql(
        f"""
        SELECT
            je.name,
            je.docstatus,
            je.company,
            je.posting_date,
            je.creation,
            je.custom_ndis_sandbox_draft_only,
            je.custom_ndis_sandbox_posting_run,
            je.custom_ndis_accounting_posting_request,
            je.custom_ndis_sandbox_acknowledgement
        FROM `tabJournal Entry` je
        WHERE {" AND ".join(conditions)}
        ORDER BY je.creation ASC
        """,
        params,
        as_dict=True,
    )

    if target_journal_entry and not rows and frappe.db.exists("Journal Entry", target_journal_entry):
        je = frappe.get_doc("Journal Entry", target_journal_entry)
        rows.append(
            frappe._dict(
                {
                    "name": je.name,
                    "docstatus": je.docstatus,
                    "company": je.company,
                    "posting_date": je.posting_date,
                    "creation": je.creation,
                    "custom_ndis_sandbox_draft_only": int(je.get("custom_ndis_sandbox_draft_only") or 0),
                    "custom_ndis_sandbox_posting_run": je.get("custom_ndis_sandbox_posting_run"),
                    "custom_ndis_accounting_posting_request": je.get("custom_ndis_accounting_posting_request"),
                    "custom_ndis_sandbox_acknowledgement": je.get("custom_ndis_sandbox_acknowledgement"),
                }
            )
        )

    return rows


def validate_candidate(row):
    reasons = []
    gl_count = get_gl_count_for_je(row.name)
    debit_total, credit_total = get_je_totals(row.name)
    age_days = date_diff(today(), getdate(row.creation))

    if not frappe.db.exists("Journal Entry", row.name):
        reasons.append("Journal Entry no longer exists.")
    if int(row.docstatus or 0) != 0:
        reasons.append("Journal Entry is not draft docstatus 0.")
    if not int(row.custom_ndis_sandbox_draft_only or 0):
        reasons.append("Journal Entry is not tagged as NDIS sandbox draft only.")
    if gl_count:
        reasons.append(f"Linked GL Entry exists: {gl_count}.")
    if not row.custom_ndis_sandbox_posting_run:
        reasons.append("Missing linked NDIS sandbox posting run.")

    return {
        "journal_entry": row.name,
        "sandbox_run": row.custom_ndis_sandbox_posting_run,
        "posting_request": row.custom_ndis_accounting_posting_request,
        "company": row.company,
        "posting_date": row.posting_date,
        "docstatus": int(row.docstatus or 0),
        "sandbox_draft_only": int(row.custom_ndis_sandbox_draft_only or 0),
        "linked_gl_entry_count": gl_count,
        "age_days": age_days,
        "total_debit": debit_total,
        "total_credit": credit_total,
        "eligible": not bool(reasons),
        "block_reason": "; ".join(reasons),
    }


def clear_links_before_delete(candidate):
    sandbox_run = candidate.get("sandbox_run")
    journal_entry = candidate.get("journal_entry")
    if sandbox_run and frappe.db.exists("NDIS Sandbox Accounting Posting Run", sandbox_run):
        frappe.db.set_value(
            "NDIS Sandbox Accounting Posting Run",
            sandbox_run,
            {
                "journal_entry": None,
                "journal_entry_docstatus": 0,
                "validation_log": f"Sandbox draft Journal Entry {journal_entry} deleted by Phase 2E cleanup.",
            },
            update_modified=False,
        )


def delete_candidate_journal_entry(candidate):
    journal_entry = candidate.get("journal_entry")
    if not journal_entry:
        return False
    clear_links_before_delete(candidate)
    frappe.delete_doc(
        "Journal Entry",
        journal_entry,
        force=1,
        ignore_permissions=True,
        ignore_missing=True,
        delete_permanently=False,
    )
    return not bool(frappe.db.exists("Journal Entry", journal_entry))


@frappe.whitelist()
def run_sandbox_accounting_cleanup(
    target_sandbox_run=None,
    target_journal_entry=None,
    older_than_days=0,
    include_cancelled_runs=1,
    delete_journal_entries=0,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_sandbox_accounting_cleanup")
    sandbox_config = validate_sandbox_config()
    candidates = [
        validate_candidate(row)
        for row in find_candidates(
            target_sandbox_run=target_sandbox_run,
            target_journal_entry=target_journal_entry,
            older_than_days=older_than_days,
            include_cancelled_runs=include_cancelled_runs,
        )
    ]
    eligible = [row for row in candidates if row["eligible"]]
    blocked = [row for row in candidates if not row["eligible"]]
    submitted_sandbox_je_count = frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 1})
    linked_gl_entry_count = sum(int(row["linked_gl_entry_count"] or 0) for row in candidates)
    errors = list(sandbox_config["errors"])

    if int(delete_journal_entries or 0):
        if acknowledgement != CLEANUP_ACK:
            errors.append(f"Invalid acknowledgement. Required: {CLEANUP_ACK}")
        if submitted_sandbox_je_count:
            errors.append(f"Submitted sandbox Journal Entries exist: {submitted_sandbox_je_count}.")
        if not eligible:
            errors.append("No eligible draft tagged sandbox Journal Entries found for deletion.")

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "delete_journal_entries": int(delete_journal_entries or 0),
        "required_acknowledgement": CLEANUP_ACK,
        "acknowledgement_ok": acknowledgement == CLEANUP_ACK,
        "sandbox_config": sandbox_config,
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "submitted_sandbox_je_count": submitted_sandbox_je_count,
        "linked_gl_entry_count": linked_gl_entry_count,
        "errors": errors,
        "candidates": candidates,
        "note": "Cleanup preview only. No Journal Entry deleted." if int(dry_run or 0) else "Sandbox cleanup requested.",
    }

    if int(dry_run or 0):
        return result

    cleanup_status = "Blocked" if errors else "Previewed"
    cleanup_mode = "Delete Draft Sandbox JE" if int(delete_journal_entries or 0) else "Preview Only"
    run = create_cleanup_run_record(
        status=cleanup_status,
        cleanup_mode=cleanup_mode,
        target_sandbox_run=target_sandbox_run,
        target_journal_entry=target_journal_entry,
        older_than_days=older_than_days,
        include_cancelled_runs=include_cancelled_runs,
        acknowledgement=acknowledgement,
        candidates=candidates,
        validation_log=result,
        notes=notes,
    )

    deleted_count = 0
    if not errors and int(delete_journal_entries or 0):
        for candidate in eligible:
            deleted = delete_candidate_journal_entry(candidate)
            deleted_count += 1 if deleted else 0
            line_name = frappe.db.get_value(
                "NDIS Sandbox Accounting Cleanup Line",
                {"cleanup_run": run.name, "journal_entry": candidate["journal_entry"]},
                "name",
            )
            if line_name:
                frappe.db.set_value(
                    "NDIS Sandbox Accounting Cleanup Line",
                    line_name,
                    {
                        "status": "Deleted" if deleted else "Blocked",
                        "journal_entry_exists_after": 0 if deleted else 1,
                        "action_taken": "Draft sandbox Journal Entry deleted." if deleted else "Deletion failed or JE still exists.",
                    },
                    update_modified=False,
                )
        frappe.db.set_value(
            "NDIS Sandbox Accounting Cleanup Run",
            run.name,
            {"status": "Cleaned", "deleted_journal_entry_count": deleted_count},
            update_modified=False,
        )

    frappe.db.commit()
    result["created"] = True
    result["cleanup_run"] = run.name
    result["cleanup_id"] = run.cleanup_id
    result["deleted_journal_entry_count"] = deleted_count
    result["status"] = "Cleaned" if deleted_count else cleanup_status
    return result


def create_cleanup_run_record(
    status,
    cleanup_mode,
    target_sandbox_run,
    target_journal_entry,
    older_than_days,
    include_cancelled_runs,
    acknowledgement,
    candidates,
    validation_log,
    notes=None,
):
    run = frappe.new_doc("NDIS Sandbox Accounting Cleanup Run")
    run.cleanup_id = make_cleanup_id()
    run.status = status
    run.cleanup_mode = cleanup_mode
    run.target_sandbox_run = target_sandbox_run
    run.target_journal_entry = target_journal_entry
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
    run.deleted_journal_entry_count = 0
    run.linked_gl_entry_count = sum(int(row["linked_gl_entry_count"] or 0) for row in candidates)
    run.submitted_sandbox_je_count = frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 1})
    run.created_on = now_datetime()
    run.created_by_user = frappe.session.user
    run.validation_log = safe_json(validation_log)
    run.notes = notes
    run.insert(ignore_permissions=True)

    for idx, candidate in enumerate(candidates, start=1):
        line = frappe.new_doc("NDIS Sandbox Accounting Cleanup Line")
        line.cleanup_run = run.name
        line.status = "Eligible" if candidate["eligible"] else "Blocked"
        line.line_no = idx
        line.sandbox_run = candidate["sandbox_run"]
        line.journal_entry = candidate["journal_entry"]
        line.journal_entry_exists_before = 1
        line.journal_entry_exists_after = 1
        line.journal_entry_docstatus = candidate["docstatus"]
        line.sandbox_draft_only = candidate["sandbox_draft_only"]
        line.linked_gl_entry_count = candidate["linked_gl_entry_count"]
        line.age_days = candidate["age_days"]
        line.posting_request = candidate["posting_request"]
        line.company = candidate["company"]
        line.posting_date = candidate["posting_date"]
        line.total_debit = candidate["total_debit"]
        line.total_credit = candidate["total_credit"]
        line.block_reason = candidate["block_reason"]
        line.action_taken = "Eligible for deletion." if candidate["eligible"] else "Blocked from deletion."
        line.insert(ignore_permissions=True)
    return run


@frappe.whitelist()
def cancel_sandbox_accounting_cleanup(cleanup_run, reason=None):
    assert_action("cancel_sandbox_accounting_cleanup")
    if not frappe.db.exists("NDIS Sandbox Accounting Cleanup Run", cleanup_run):
        frappe.throw(_("Sandbox Accounting Cleanup Run not found: {0}").format(cleanup_run))
    frappe.db.set_value(
        "NDIS Sandbox Accounting Cleanup Run",
        cleanup_run,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "validation_log": reason or "Sandbox cleanup run cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Sandbox Accounting Cleanup Line`
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
        "note": "Cleanup run cancelled. Already-deleted draft sandbox JEs are not recreated.",
    }


@frappe.whitelist()
def quick_sandbox_cleanup_summary(limit=20):
    runs = frappe.get_all(
        "NDIS Sandbox Accounting Cleanup Run",
        fields=[
            "name",
            "cleanup_id",
            "status",
            "cleanup_mode",
            "candidate_count",
            "eligible_count",
            "blocked_count",
            "deleted_journal_entry_count",
            "linked_gl_entry_count",
            "submitted_sandbox_je_count",
            "created_on",
            "created_by_user",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Sandbox Accounting Cleanup Line",
        fields=[
            "name",
            "cleanup_run",
            "status",
            "sandbox_run",
            "journal_entry",
            "journal_entry_exists_before",
            "journal_entry_exists_after",
            "journal_entry_docstatus",
            "sandbox_draft_only",
            "linked_gl_entry_count",
            "age_days",
            "action_taken",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    guardrails = {
        "draft_sandbox_journal_entries": frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 0}),
        "submitted_sandbox_journal_entries": frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 1}),
        "gl_entries_today": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "payment_entries_today": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
    }
    return {
        "runs": runs,
        "lines": lines,
        "guardrails": guardrails,
        "required_acknowledgement": CLEANUP_ACK,
        "note": "Sandbox cleanup summary only. Cleanup can delete draft tagged sandbox JEs only. It cannot delete submitted JEs or any JE with GL Entries.",
    }


def execute_cleanup_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["status", "cleanup_mode"]:
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
        {"fieldname": "cleanup_run", "label": _("Cleanup Run"), "fieldtype": "Link", "options": "NDIS Sandbox Accounting Cleanup Run", "width": 220},
        {"fieldname": "cleanup_id", "label": _("Cleanup ID"), "fieldtype": "Data", "width": 300},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "cleanup_mode", "label": _("Cleanup Mode"), "fieldtype": "Data", "width": 190},
        {"fieldname": "candidate_count", "label": _("Candidates"), "fieldtype": "Int", "width": 100},
        {"fieldname": "eligible_count", "label": _("Eligible"), "fieldtype": "Int", "width": 90},
        {"fieldname": "blocked_count", "label": _("Blocked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "deleted_journal_entry_count", "label": _("Deleted JEs"), "fieldtype": "Int", "width": 110},
        {"fieldname": "linked_gl_entry_count", "label": _("Linked GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "submitted_sandbox_je_count", "label": _("Submitted Sandbox JEs"), "fieldtype": "Int", "width": 160},
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
            r.deleted_journal_entry_count,
            r.linked_gl_entry_count,
            r.submitted_sandbox_je_count,
            r.created_on,
            r.created_by_user
        FROM `tabNDIS Sandbox Accounting Cleanup Run` r
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
                {"name": "Deleted", "values": [int(row.deleted_journal_entry_count or 0) for row in data[:20]]},
                {"name": "Blocked", "values": [int(row.blocked_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Cleanup Runs"), "datatype": "Int"},
        {"value": sum(int(row.deleted_journal_entry_count or 0) for row in data), "indicator": "Green", "label": _("Deleted Draft JEs"), "datatype": "Int"},
        {"value": sum(int(row.blocked_count or 0) for row in data), "indicator": "Red", "label": _("Blocked Lines"), "datatype": "Int"},
        {"value": sum(int(row.submitted_sandbox_je_count or 0) for row in data), "indicator": "Red", "label": _("Submitted Sandbox JEs"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_hygiene_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["je.custom_ndis_sandbox_draft_only = 1"]
    params = {}
    if filters.get("docstatus") not in [None, ""]:
        conditions.append("je.docstatus = %(docstatus)s")
        params["docstatus"] = int(filters.get("docstatus"))
    if filters.get("sandbox_run"):
        conditions.append("je.custom_ndis_sandbox_posting_run = %(sandbox_run)s")
        params["sandbox_run"] = filters.get("sandbox_run")
    if filters.get("min_age_days") not in [None, ""]:
        conditions.append("DATE(je.creation) <= DATE_SUB(CURDATE(), INTERVAL %(min_age_days)s DAY)")
        params["min_age_days"] = int(filters.get("min_age_days"))
    params["currency"] = currency()

    columns = [
        {"fieldname": "journal_entry", "label": _("Journal Entry"), "fieldtype": "Link", "options": "Journal Entry", "width": 190},
        {"fieldname": "docstatus", "label": _("Docstatus"), "fieldtype": "Int", "width": 90},
        {"fieldname": "sandbox_run", "label": _("Sandbox Run"), "fieldtype": "Link", "options": "NDIS Sandbox Accounting Posting Run", "width": 220},
        {"fieldname": "posting_request", "label": _("Posting Request"), "fieldtype": "Link", "options": "NDIS Accounting Posting Request", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "age_days", "label": _("Age Days"), "fieldtype": "Int", "width": 90},
        {"fieldname": "total_debit", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "total_credit", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "gl_count", "label": _("GL Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "hygiene_status", "label": _("Hygiene Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            je.name AS journal_entry,
            je.docstatus,
            je.custom_ndis_sandbox_posting_run AS sandbox_run,
            je.custom_ndis_accounting_posting_request AS posting_request,
            je.company,
            je.posting_date,
            DATEDIFF(CURDATE(), DATE(je.creation)) AS age_days,
            COALESCE(SUM(jea.debit_in_account_currency), 0) AS total_debit,
            COALESCE(SUM(jea.credit_in_account_currency), 0) AS total_credit,
            (
                SELECT COUNT(*)
                FROM `tabGL Entry` gle
                WHERE gle.voucher_type = 'Journal Entry'
                AND gle.voucher_no = je.name
            ) AS gl_count,
            CASE
                WHEN je.docstatus = 1 THEN 'Submitted - Critical'
                WHEN (
                    SELECT COUNT(*)
                    FROM `tabGL Entry` gle
                    WHERE gle.voucher_type = 'Journal Entry'
                    AND gle.voucher_no = je.name
                ) > 0 THEN 'GL Exists - Critical'
                WHEN DATEDIFF(CURDATE(), DATE(je.creation)) >= 7 THEN 'Old Draft'
                ELSE 'Draft OK'
            END AS hygiene_status,
            %(currency)s AS currency
        FROM `tabJournal Entry` je
        LEFT JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        WHERE {" AND ".join(conditions)}
        GROUP BY je.name
        ORDER BY je.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.hygiene_status or "Unknown"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "JEs", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Sandbox JEs"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 0]), "indicator": "Green", "label": _("Draft"), "datatype": "Int"},
        {"value": len([row for row in data if row.docstatus == 1]), "indicator": "Red", "label": _("Submitted"), "datatype": "Int"},
        {"value": sum(int(row.gl_count or 0) for row in data), "indicator": "Red", "label": _("Linked GL Entries"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
