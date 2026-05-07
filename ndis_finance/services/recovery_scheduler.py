import json
import traceback

import frappe
from frappe.utils import add_days, get_datetime, now_datetime, nowdate

from ndis_finance.services.permissions import assert_action
from ndis_finance.services.recovery_engine import create_recovery_cases_from_open_leakages


OPEN_RECOVERY_STATUSES = ["Open", "In Follow Up", "Waiting For Response", "Escalated"]
CLAIM_EXCEPTION_STATUSES = ["Short Paid", "Rejected", "Reclaim Required"]


def make_run_id(run_type="Manual"):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    prefix = "NDIS-REC-AUTO"

    if run_type == "Scheduled":
        prefix = "NDIS-REC-SCH"

    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def sql_count(query, params=None):
    result = frappe.db.sql(query, params or {}, as_dict=True)
    if not result:
        return 0

    return int(result[0].get("count") or 0)


def sql_rows(query, params=None, limit=20):
    params = dict(params or {})
    params["limit"] = int(limit or 20)
    return frappe.db.sql(query, params, as_dict=True)


@frappe.whitelist()
def run_daily_recovery_monitor(
    run_type="Manual",
    create_missing_cases=1,
    assigned_to=None,
    escalation_overdue_days=3,
    preview_limit=20,
):
    """
    Daily NDIS recovery monitoring.

    Safe behaviour:
    - Does not send emails.
    - Does not create Payment Entry.
    - Does not create Journal Entry.
    - Does not create GL Entry.
    - Does not allocate payments.
    - Optionally creates missing Recovery Cases from open Funding Leakage only.
    """

    assert_action("run_recovery_automation")

    run_id = make_run_id(run_type=run_type)

    log = frappe.new_doc("NDIS Recovery Automation Log")
    log.run_id = run_id
    log.run_type = run_type
    log.status = "Started"
    log.started_on = now_datetime()
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        summary = build_recovery_monitor_summary(
            escalation_overdue_days=escalation_overdue_days,
            preview_limit=preview_limit,
        )

        created_recovery_cases = 0
        create_missing_cases = int(create_missing_cases or 0)

        if create_missing_cases:
            previous_flag = bool(
                getattr(frappe.flags, "ndis_allow_recovery_case_creation", False)
            )
            frappe.flags.ndis_allow_recovery_case_creation = True
            try:
                creation_result = create_recovery_cases_from_open_leakages(
                    limit=100,
                    assigned_to=assigned_to,
                )
            finally:
                frappe.flags.ndis_allow_recovery_case_creation = previous_flag

            created_recovery_cases = int(creation_result.get("created") or 0)
            summary["created_recovery_cases_result"] = creation_result

            summary["after_case_creation"] = build_recovery_monitor_summary(
                escalation_overdue_days=escalation_overdue_days,
                preview_limit=preview_limit,
            )

        counts = summary.get("counts", {})
        total_issues_found = (
            int(counts.get("due_recovery_cases") or 0)
            + int(counts.get("overdue_recovery_cases") or 0)
            + int(counts.get("open_leakage_without_case") or 0)
            + int(counts.get("claim_exceptions_without_case") or 0)
            + int(counts.get("approved_drafts_not_sent") or 0)
            + int(counts.get("escalation_candidates") or 0)
        )

        status = "Completed"
        if total_issues_found > 0:
            status = "Completed With Exceptions"

        frappe.db.set_value(
            "NDIS Recovery Automation Log",
            log.name,
            {
                "status": status,
                "completed_on": now_datetime(),
                "due_recovery_cases": int(counts.get("due_recovery_cases") or 0),
                "overdue_recovery_cases": int(counts.get("overdue_recovery_cases") or 0),
                "open_leakage_without_case": int(counts.get("open_leakage_without_case") or 0),
                "claim_exceptions_without_case": int(
                    counts.get("claim_exceptions_without_case") or 0
                ),
                "approved_drafts_not_sent": int(counts.get("approved_drafts_not_sent") or 0),
                "escalation_candidates": int(counts.get("escalation_candidates") or 0),
                "created_recovery_cases": created_recovery_cases,
                "total_issues_found": total_issues_found,
                "summary_json": json.dumps(summary, default=str, indent=2),
            },
            update_modified=False,
        )

        frappe.db.commit()

        return {
            "run_id": run_id,
            "automation_log": log.name,
            "status": status,
            "created_recovery_cases": created_recovery_cases,
            "total_issues_found": total_issues_found,
            "summary": summary,
            "note": "No emails sent. No accounting entries created. No payment allocation performed.",
        }

    except Exception:
        error = traceback.format_exc()

        frappe.db.set_value(
            "NDIS Recovery Automation Log",
            log.name,
            {
                "status": "Failed",
                "completed_on": now_datetime(),
                "error_log": error,
            },
            update_modified=False,
        )

        frappe.db.commit()
        frappe.log_error(error, "NDIS Recovery Automation Failed")
        raise


def daily_recovery_monitor_job():
    """
    Scheduler entry point. This runs daily through hooks.py.
    """

    return run_daily_recovery_monitor(
        run_type="Scheduled",
        create_missing_cases=1,
        assigned_to=None,
        escalation_overdue_days=3,
        preview_limit=20,
    )


@frappe.whitelist()
def build_recovery_monitor_summary(escalation_overdue_days=3, preview_limit=20):
    escalation_cutoff = add_days(nowdate(), -int(escalation_overdue_days or 3))

    counts = {
        "due_recovery_cases": count_due_recovery_cases(),
        "overdue_recovery_cases": count_overdue_recovery_cases(),
        "open_leakage_without_case": count_open_leakage_without_case(),
        "claim_exceptions_without_case": count_claim_exceptions_without_case(),
        "approved_drafts_not_sent": count_approved_drafts_not_sent(),
        "escalation_candidates": count_escalation_candidates(escalation_cutoff),
    }

    previews = {
        "due_recovery_cases": get_due_recovery_cases(preview_limit),
        "overdue_recovery_cases": get_overdue_recovery_cases(preview_limit),
        "open_leakage_without_case": get_open_leakage_without_case(preview_limit),
        "claim_exceptions_without_case": get_claim_exceptions_without_case(preview_limit),
        "approved_drafts_not_sent": get_approved_drafts_not_sent(preview_limit),
        "escalation_candidates": get_escalation_candidates(escalation_cutoff, preview_limit),
    }

    return {
        "date": nowdate(),
        "escalation_overdue_days": int(escalation_overdue_days or 3),
        "escalation_cutoff": escalation_cutoff,
        "counts": counts,
        "previews": previews,
    }


def count_due_recovery_cases():
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Recovery Case`
        WHERE status IN %(statuses)s
        AND next_follow_up_date = %(today)s
        """,
        {"statuses": tuple(OPEN_RECOVERY_STATUSES), "today": nowdate()},
    )


def count_overdue_recovery_cases():
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Recovery Case`
        WHERE status IN %(statuses)s
        AND next_follow_up_date < %(today)s
        """,
        {"statuses": tuple(OPEN_RECOVERY_STATUSES), "today": nowdate()},
    )


def count_open_leakage_without_case():
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Funding Leakage Register`
        WHERE status IN ('Open', 'In Review')
        AND (recovery_case IS NULL OR recovery_case = '')
        """,
    )


def count_claim_exceptions_without_case():
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Claim Line`
        WHERE claim_status IN %(statuses)s
        AND (recovery_case IS NULL OR recovery_case = '')
        """,
        {"statuses": tuple(CLAIM_EXCEPTION_STATUSES)},
    )


def count_approved_drafts_not_sent():
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Recovery Email Draft`
        WHERE status = 'Approved'
        """,
    )


def count_escalation_candidates(escalation_cutoff):
    return sql_count(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Recovery Case`
        WHERE status IN ('Open', 'In Follow Up', 'Waiting For Response')
        AND next_follow_up_date <= %(escalation_cutoff)s
        """,
        {"escalation_cutoff": escalation_cutoff},
    )


def get_due_recovery_cases(limit=20):
    return sql_rows(
        """
        SELECT
            name,
            case_id,
            case_type,
            status,
            priority,
            assigned_to,
            participant,
            sales_invoice,
            outstanding_amount,
            next_follow_up_date
        FROM `tabNDIS Recovery Case`
        WHERE status IN %(statuses)s
        AND next_follow_up_date = %(today)s
        ORDER BY priority DESC, outstanding_amount DESC
        LIMIT %(limit)s
        """,
        {"statuses": tuple(OPEN_RECOVERY_STATUSES), "today": nowdate()},
        limit=limit,
    )


def get_overdue_recovery_cases(limit=20):
    return sql_rows(
        """
        SELECT
            name,
            case_id,
            case_type,
            status,
            priority,
            assigned_to,
            participant,
            sales_invoice,
            outstanding_amount,
            next_follow_up_date
        FROM `tabNDIS Recovery Case`
        WHERE status IN %(statuses)s
        AND next_follow_up_date < %(today)s
        ORDER BY next_follow_up_date ASC, outstanding_amount DESC
        LIMIT %(limit)s
        """,
        {"statuses": tuple(OPEN_RECOVERY_STATUSES), "today": nowdate()},
        limit=limit,
    )


def get_open_leakage_without_case(limit=20):
    return sql_rows(
        """
        SELECT
            name,
            leakage_type,
            status,
            participant,
            house,
            service_date,
            expected_amount,
            actual_amount,
            variance_amount,
            severity,
            claim_line,
            sales_invoice
        FROM `tabNDIS Funding Leakage Register`
        WHERE status IN ('Open', 'In Review')
        AND (recovery_case IS NULL OR recovery_case = '')
        ORDER BY variance_amount DESC, modified ASC
        LIMIT %(limit)s
        """,
        {},
        limit=limit,
    )


def get_claim_exceptions_without_case(limit=20):
    return sql_rows(
        """
        SELECT
            name,
            claim_batch,
            claim_status,
            payment_status,
            participant,
            sales_invoice,
            service_date,
            support_item_number,
            claim_amount,
            paid_amount,
            shortfall_amount,
            recovery_status
        FROM `tabNDIS Claim Line`
        WHERE claim_status IN %(statuses)s
        AND (recovery_case IS NULL OR recovery_case = '')
        ORDER BY shortfall_amount DESC, modified ASC
        LIMIT %(limit)s
        """,
        {"statuses": tuple(CLAIM_EXCEPTION_STATUSES)},
        limit=limit,
    )


def get_approved_drafts_not_sent(limit=20):
    return sql_rows(
        """
        SELECT
            name,
            draft_id,
            draft_type,
            recovery_case,
            participant,
            sales_invoice,
            recipient_email,
            subject,
            approved_on,
            approved_by
        FROM `tabNDIS Recovery Email Draft`
        WHERE status = 'Approved'
        ORDER BY approved_on ASC
        LIMIT %(limit)s
        """,
        {},
        limit=limit,
    )


def get_escalation_candidates(escalation_cutoff, limit=20):
    return sql_rows(
        """
        SELECT
            name,
            case_id,
            case_type,
            status,
            priority,
            assigned_to,
            participant,
            sales_invoice,
            outstanding_amount,
            next_follow_up_date,
            last_follow_up_on
        FROM `tabNDIS Recovery Case`
        WHERE status IN ('Open', 'In Follow Up', 'Waiting For Response')
        AND next_follow_up_date <= %(escalation_cutoff)s
        ORDER BY next_follow_up_date ASC, outstanding_amount DESC
        LIMIT %(limit)s
        """,
        {"escalation_cutoff": escalation_cutoff},
        limit=limit,
    )


@frappe.whitelist()
def quick_automation_log_summary(limit=20):
    return frappe.get_all(
        "NDIS Recovery Automation Log",
        fields=[
            "name",
            "run_id",
            "run_type",
            "status",
            "started_on",
            "completed_on",
            "due_recovery_cases",
            "overdue_recovery_cases",
            "open_leakage_without_case",
            "claim_exceptions_without_case",
            "approved_drafts_not_sent",
            "escalation_candidates",
            "created_recovery_cases",
            "total_issues_found",
        ],
        order_by="started_on desc",
        limit=int(limit or 20),
    )
