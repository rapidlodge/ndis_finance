import frappe
from frappe import _

from ndis_finance.setup.install import _create_doctype


PHASE1K_DOCTYPES = [
    "NDIS Recovery Automation Log",
]

SCHEDULER_JOB = "ndis_finance.services.recovery_scheduler.daily_recovery_monitor_job"


@frappe.whitelist()
def install():
    validate_phase1j()
    create_recovery_automation_log_doctype()
    frappe.db.commit()
    return health_check()


def validate_phase1j():
    required = [
        "NDIS Recovery Case",
        "NDIS Recovery Activity",
        "NDIS Recovery Email Draft",
        "NDIS Funding Leakage Register",
        "NDIS Claim Line",
        "NDIS Payment Reconciliation Batch",
        "NDIS Payment Reconciliation Line",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1K requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_recovery_automation_log_doctype():
    _create_doctype(
        name="NDIS Recovery Automation Log",
        autoname="field:run_id",
        title_field="run_id",
        fields=[
            {
                "fieldname": "run_id",
                "label": "Run ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "run_type",
                "label": "Run Type",
                "fieldtype": "Select",
                "options": "\nManual\nScheduled",
                "default": "Manual",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nStarted\nCompleted\nCompleted With Exceptions\nFailed",
                "default": "Started",
                "in_list_view": 1,
            },
            {
                "fieldname": "started_on",
                "label": "Started On",
                "fieldtype": "Datetime",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "completed_on",
                "label": "Completed On",
                "fieldtype": "Datetime",
                "read_only": 1,
            },
            {
                "fieldname": "count_section",
                "label": "Exception Counts",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "due_recovery_cases",
                "label": "Due Recovery Cases",
                "fieldtype": "Int",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "overdue_recovery_cases",
                "label": "Overdue Recovery Cases",
                "fieldtype": "Int",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "open_leakage_without_case",
                "label": "Open Leakage Without Recovery Case",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "claim_exceptions_without_case",
                "label": "Claim Exceptions Without Recovery Case",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "approved_drafts_not_sent",
                "label": "Approved Drafts Not Sent",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "escalation_candidates",
                "label": "Escalation Candidates",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "created_recovery_cases",
                "label": "Created Recovery Cases",
                "fieldtype": "Int",
                "read_only": 1,
            },
            {
                "fieldname": "total_issues_found",
                "label": "Total Issues Found",
                "fieldtype": "Int",
                "read_only": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "detail_section",
                "label": "Details",
                "fieldtype": "Section Break",
            },
            {
                "fieldname": "summary_json",
                "label": "Summary JSON",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
            {
                "fieldname": "error_log",
                "label": "Error Log",
                "fieldtype": "Long Text",
                "read_only": 1,
            },
        ],
    )


@frappe.whitelist()
def health_check():
    doctypes = {
        dt: bool(frappe.db.exists("DocType", dt))
        for dt in PHASE1K_DOCTYPES
    }

    hooks = frappe.get_hooks()
    scheduler_events = hooks.get("scheduler_events", {})
    daily_jobs = []

    if isinstance(scheduler_events, dict):
        daily_jobs = scheduler_events.get("daily", []) or []

    return {
        "doctypes": doctypes,
        "scheduler": {
            "daily_job_registered": SCHEDULER_JOB in daily_jobs,
            "job": SCHEDULER_JOB,
        },
        "service_import": can_import_scheduler_service(),
    }


def can_import_scheduler_service():
    try:
        from ndis_finance.services.recovery_scheduler import run_daily_recovery_monitor

        return callable(run_daily_recovery_monitor)
    except Exception:
        return False
