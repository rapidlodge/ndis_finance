import json

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


REQUIRED_ACK = "I_CONFIRM_NDIS_FINANCE_ACCOUNTING_INTEGRATION_REVIEWED"

PHASE_HEALTH_CHECKS = [
    ("Phase 1M", "ndis_finance.setup.phase1m.health_check"),
    ("Phase 1N", "ndis_finance.setup.phase1n.health_check"),
    ("Phase 1O", "ndis_finance.setup.phase1o.health_check"),
    ("Phase 1P", "ndis_finance.setup.phase1p.health_check"),
    ("Phase 1Q", "ndis_finance.setup.phase1q.health_check"),
    ("Phase 1R", "ndis_finance.setup.phase1r.health_check"),
    ("Phase 1S", "ndis_finance.setup.phase1s.health_check"),
    ("Phase 1T", "ndis_finance.setup.phase1t.health_check"),
    ("Phase 1U", "ndis_finance.setup.phase1u.health_check"),
    ("Phase 1V", "ndis_finance.setup.phase1v.health_check"),
    ("Phase 1W", "ndis_finance.setup.phase1w.health_check"),
    ("Phase 1X", "ndis_finance.setup.phase1x.health_check"),
    ("Phase 1Y", "ndis_finance.setup.phase1y.health_check"),
    ("Phase 1Z", "ndis_finance.setup.phase1z.health_check"),
]

REQUIRED_DOCTYPES = [
    "NDIS Claim Line",
    "NDIS Cost Pool",
    "NDIS Cost Allocation Entry",
    "NDIS Payroll Cost Import",
    "NDIS Executive Dashboard Snapshot",
    "NDIS Executive Exception Alert",
    "NDIS Executive Exception Rule",
    "NDIS Executive Exception Action Plan",
    "NDIS Executive Governance Pack",
    "NDIS Finance Production Readiness Check",
    "NDIS Finance Production Readiness Check Item",
]

SENSITIVE_ACCOUNTING_DOCTYPES = ["Payment Entry", "Journal Entry", "GL Entry"]


def make_check_id(readiness_type="Pre-Accounting Integration"):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    safe_type = frappe.scrub(readiness_type or "Readiness").replace("_", "-").upper()
    return f"NDIS-FINANCE-READINESS-{safe_type}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def add_item(
    items,
    status,
    severity,
    category,
    check_key,
    check_label,
    detail,
    recommendation=None,
    source_doctype=None,
    source_name=None,
):
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


def contains_false_or_none(value):
    if value is False or value is None:
        return True
    if isinstance(value, dict):
        return any(contains_false_or_none(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_false_or_none(child) for child in value)
    return False


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def evaluate_phase_health_checks(items):
    for label, method_path in PHASE_HEALTH_CHECKS:
        try:
            result = frappe.get_attr(method_path)()
            if contains_false_or_none(result):
                add_item(
                    items,
                    "Blocker",
                    "Critical",
                    "Regression Health",
                    method_path,
                    f"{label} health check",
                    "Health check returned false/null values.",
                    "Open the phase health output and fix the failing items before considering accounting integration.",
                )
            else:
                add_item(items, "Pass", "Low", "Regression Health", method_path, f"{label} health check", "Health check returned clean result.")
        except Exception as exc:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Regression Health",
                method_path,
                f"{label} health check",
                f"Health check failed with error: {str(exc)}",
                "Fix the failed health check import/execution before proceeding.",
            )


def evaluate_required_doctypes(items):
    missing = [dt for dt in REQUIRED_DOCTYPES if not frappe.db.exists("DocType", dt)]
    if missing:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Required DocTypes",
            "required_doctypes",
            "Required NDIS Finance DocTypes",
            "Missing DocTypes: " + ", ".join(missing),
            "Run the relevant phase installer/migration before continuing.",
        )
    else:
        add_item(items, "Pass", "Low", "Required DocTypes", "required_doctypes", "Required NDIS Finance DocTypes", "All required DocTypes exist.")


def get_guardrail_counts():
    counts = {}
    for dt in SENSITIVE_ACCOUNTING_DOCTYPES:
        counts[dt] = frappe.db.count(dt, {"creation": [">=", today()]}) if frappe.db.exists("DocType", dt) else 0
    return counts


def evaluate_accounting_guardrails(items, strict_accounting_guardrail=0):
    counts = get_guardrail_counts()
    total = sum(int(value or 0) for value in counts.values())
    if total == 0:
        add_item(
            items,
            "Pass",
            "Low",
            "Accounting Guardrail",
            "accounting_guardrail_today",
            "Accounting movement count today",
            "Payment Entry, Journal Entry and GL Entry counts for today are all zero.",
        )
        return counts

    status = "Blocker" if int(strict_accounting_guardrail or 0) else "Warning"
    severity = "Critical" if int(strict_accounting_guardrail or 0) else "Medium"
    add_item(
        items,
        status,
        severity,
        "Accounting Guardrail",
        "accounting_guardrail_today",
        "Accounting movement count today",
        f"Today's counts: Payment Entry={counts.get('Payment Entry')}, Journal Entry={counts.get('Journal Entry')}, GL Entry={counts.get('GL Entry')}.",
        "Confirm these were not created by NDIS Finance smoke tests or enable strict guardrail only in a controlled test window.",
    )
    return counts


def evaluate_exception_alerts(items):
    critical = frappe.db.count("NDIS Executive Exception Alert", {"status": ["in", ["Open", "In Review"]], "severity": "Critical"})
    high = frappe.db.count("NDIS Executive Exception Alert", {"status": ["in", ["Open", "In Review"]], "severity": "High"})

    if critical:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Executive Exceptions",
            "open_critical_exception_alerts",
            "Open critical executive exception alerts",
            f"{critical} critical alert(s) are still open or in review.",
            "Resolve or formally sign off critical executive exceptions before accounting integration.",
        )
    else:
        add_item(items, "Pass", "Low", "Executive Exceptions", "open_critical_exception_alerts", "Open critical executive exception alerts", "No open critical executive exception alerts found.")

    if high:
        add_item(
            items,
            "Warning",
            "High",
            "Executive Exceptions",
            "open_high_exception_alerts",
            "Open high executive exception alerts",
            f"{high} high-severity alert(s) are still open or in review.",
            "Review high-severity exceptions before accounting integration.",
        )
    else:
        add_item(items, "Pass", "Low", "Executive Exceptions", "open_high_exception_alerts", "Open high executive exception alerts", "No open high executive exception alerts found.")

    return critical, high


def evaluate_action_plans(items):
    overdue_critical = frappe.db.sql(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Executive Exception Action Plan`
        WHERE status NOT IN ('Completed', 'Cancelled')
        AND priority = 'Critical'
        AND (due_date < CURDATE() OR overdue_steps > 0 OR status IN ('Overdue', 'Escalated'))
        """,
        as_dict=True,
    )[0].count
    overdue_any = frappe.db.sql(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Executive Exception Action Plan`
        WHERE status NOT IN ('Completed', 'Cancelled')
        AND (due_date < CURDATE() OR overdue_steps > 0 OR status = 'Overdue')
        """,
        as_dict=True,
    )[0].count

    if overdue_critical:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Action Plans",
            "overdue_critical_action_plans",
            "Overdue critical action plans",
            f"{overdue_critical} critical overdue/escalated action plan(s) exist.",
            "Complete, resolve, or formally sign off critical action plans before accounting integration.",
        )
    else:
        add_item(items, "Pass", "Low", "Action Plans", "overdue_critical_action_plans", "Overdue critical action plans", "No overdue critical action plans found.")

    if overdue_any:
        add_item(
            items,
            "Warning",
            "Medium",
            "Action Plans",
            "overdue_action_plans",
            "Overdue action plans",
            f"{overdue_any} overdue action plan(s) exist.",
            "Review overdue action plan report.",
        )
    else:
        add_item(items, "Pass", "Low", "Action Plans", "overdue_action_plans", "Overdue action plans", "No overdue action plans found.")

    return overdue_critical, overdue_any


def evaluate_payroll_mapping(items):
    unmapped = frappe.db.sql(
        """
        SELECT COALESCE(SUM(unmapped_line_count), 0) AS count
        FROM `tabNDIS Payroll Cost Import`
        WHERE status != 'Cancelled'
        """,
        as_dict=True,
    )[0].count
    unmapped = int(unmapped or 0)
    if unmapped:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Payroll Cost Bridge",
            "unmapped_payroll_lines",
            "Unmapped payroll lines",
            f"{unmapped} unmapped payroll line(s) found.",
            "Map Employee NDIS payroll costing fields and re-run payroll cost import before accounting integration.",
        )
    else:
        add_item(items, "Pass", "Low", "Payroll Cost Bridge", "unmapped_payroll_lines", "Unmapped payroll lines", "No unmapped payroll lines found.")
    return unmapped


def evaluate_leakage(items):
    if not frappe.db.exists("DocType", "NDIS Funding Leakage Register"):
        add_item(
            items,
            "Warning",
            "Medium",
            "Funding Leakage",
            "funding_leakage_doctype",
            "Funding leakage register",
            "NDIS Funding Leakage Register DocType not found.",
            "Confirm leakage phase is installed if this environment should have leakage controls.",
        )
        return 0

    high_critical = frappe.db.count(
        "NDIS Funding Leakage Register",
        {"status": ["in", ["Open", "In Review"]], "severity": ["in", ["High", "Critical"]]},
    )
    if high_critical:
        add_item(
            items,
            "Warning",
            "High",
            "Funding Leakage",
            "open_high_critical_leakage",
            "Open high/critical funding leakage",
            f"{high_critical} high/critical open leakage record(s) exist.",
            "Review leakage recovery and action plans before accounting integration.",
        )
    else:
        add_item(items, "Pass", "Low", "Funding Leakage", "open_high_critical_leakage", "Open high/critical funding leakage", "No high/critical open leakage records found.")
    return high_critical


def evaluate_unsafe_accounting_hooks(items):
    unsafe = []
    hooks = frappe.get_hooks()

    def walk_hook_entries(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from walk_hook_entries(child, child_path)
        elif isinstance(value, (list, tuple, set)):
            for idx, child in enumerate(value):
                yield from walk_hook_entries(child, f"{path}[{idx}]")
        else:
            yield path, str(value)

    for hook_name in ["doc_events", "scheduler_events"]:
        hook_value = hooks.get(hook_name)
        if not hook_value:
            continue

        risky_keywords = [
            "create_payment_entry",
            "make_payment_entry",
            "create_journal_entry",
            "make_journal_entry",
            "gl_entry",
            "submit_payment",
            "allocate_payment",
        ]

        for path, hook_entry in walk_hook_entries(hook_value, hook_name):
            if "ndis_finance" not in hook_entry:
                continue

            for sensitive_dt in SENSITIVE_ACCOUNTING_DOCTYPES:
                if sensitive_dt in path:
                    unsafe.append(f"{path}: {sensitive_dt}")

            for keyword in risky_keywords:
                if keyword in hook_entry.lower():
                    unsafe.append(f"{path}: {keyword}")

    unsafe = sorted(set(unsafe))
    if unsafe:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Accounting Hooks",
            "unsafe_accounting_hooks",
            "Unsafe accounting hooks",
            "Potential unsafe accounting hook(s): " + ", ".join(unsafe),
            "Remove/disable unsafe accounting hooks before accounting integration readiness can pass.",
        )
    else:
        add_item(items, "Pass", "Low", "Accounting Hooks", "unsafe_accounting_hooks", "Unsafe accounting hooks", "No NDIS Finance accounting-posting hooks detected.")
    return len(unsafe)


def evaluate_fixture_safety(items):
    from ndis_finance import hooks as ndis_finance_hooks

    fixtures = getattr(ndis_finance_hooks, "fixtures", []) or []
    warnings = []
    sensitive = ["Custom Field", "Report", "DocType", "Role", "Workspace"]
    for fixture in fixtures:
        if isinstance(fixture, dict):
            dt = fixture.get("dt")
            filters = fixture.get("filters")
            if dt in sensitive and not filters:
                warnings.append(dt)
        elif fixture in sensitive:
            warnings.append(str(fixture))

    warnings = sorted(set(warnings))
    if warnings:
        add_item(
            items,
            "Warning",
            "Medium",
            "Fixture Safety",
            "broad_fixture_filters",
            "Broad fixture filters",
            "Broad fixture export detected for: " + ", ".join(warnings),
            "Review hooks.py fixture filters to avoid fixture pollution before production deployment.",
        )
    else:
        add_item(items, "Pass", "Low", "Fixture Safety", "broad_fixture_filters", "Broad fixture filters", "No broad sensitive fixture filters detected.")
    return len(warnings)


def evaluate_governance_pack(items):
    latest = frappe.get_all(
        "NDIS Executive Governance Pack",
        filters={"status": ["!=", "Cancelled"]},
        fields=["name", "status", "pack_id", "pack_date", "governance_score", "governance_status", "management_sign_off"],
        order_by="pack_date desc, creation desc",
        limit=1,
    )
    if not latest:
        add_item(
            items,
            "Warning",
            "Medium",
            "Governance Pack",
            "latest_governance_pack",
            "Latest governance pack",
            "No non-cancelled governance pack found.",
            "Create and sign off a governance pack before production accounting integration.",
        )
        return None

    pack = latest[0]
    if not int(pack.management_sign_off or 0):
        add_item(
            items,
            "Warning",
            "High",
            "Governance Pack",
            "latest_governance_pack_signoff",
            "Latest governance pack sign-off",
            f"Latest governance pack {pack.pack_id} is not signed off.",
            "Management should review and sign off the governance pack before accounting integration.",
            "NDIS Executive Governance Pack",
            pack.name,
        )
    else:
        add_item(
            items,
            "Pass",
            "Low",
            "Governance Pack",
            "latest_governance_pack_signoff",
            "Latest governance pack sign-off",
            f"Latest governance pack {pack.pack_id} is signed off.",
            None,
            "NDIS Executive Governance Pack",
            pack.name,
        )
    return pack


def evaluate_scheduler_visibility(items):
    scheduler_events = frappe.get_hooks().get("scheduler_events", {}) or {}
    daily_jobs = scheduler_events.get("daily", []) if isinstance(scheduler_events, dict) else []
    expected_jobs = [
        "ndis_finance.services.executive_snapshots.daily_executive_dashboard_snapshot_job",
        "ndis_finance.services.executive_exceptions.daily_executive_exception_evaluation_job",
        "ndis_finance.services.executive_action_plans.daily_action_plan_overdue_monitor_job",
    ]
    missing = [job for job in expected_jobs if job not in daily_jobs]
    if missing:
        add_item(
            items,
            "Warning",
            "Medium",
            "Scheduler",
            "scheduler_jobs",
            "Executive scheduler jobs",
            "Missing daily scheduler jobs: " + ", ".join(missing),
            "Review hooks.py scheduler registration.",
        )
    else:
        add_item(items, "Pass", "Low", "Scheduler", "scheduler_jobs", "Executive scheduler jobs", "Expected executive scheduler jobs are registered.")


def summarise_items(items):
    return {
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


@frappe.whitelist()
def run_production_readiness_check(
    readiness_type="Pre-Accounting Integration",
    strict_accounting_guardrail=0,
    dry_run=0,
    acknowledgement=None,
    notes=None,
):
    assert_action("run_production_readiness_check")

    items = []
    evaluate_required_doctypes(items)
    evaluate_phase_health_checks(items)
    guardrail_counts = evaluate_accounting_guardrails(items, strict_accounting_guardrail)
    critical_alerts, high_alerts = evaluate_exception_alerts(items)
    overdue_critical_plans, overdue_any_plans = evaluate_action_plans(items)
    unmapped_payroll_lines = evaluate_payroll_mapping(items)
    open_leakage_count = evaluate_leakage(items)
    unsafe_hook_count = evaluate_unsafe_accounting_hooks(items)
    fixture_warning_count = evaluate_fixture_safety(items)
    latest_pack = evaluate_governance_pack(items)
    evaluate_scheduler_visibility(items)

    summary = summarise_items(items)
    ack_ok = acknowledgement == REQUIRED_ACK
    production_ready_allowed = bool(summary["blocker_count"] == 0 and ack_ok)
    if summary["blocker_count"]:
        status = "Blocked"
    elif summary["warning_count"] or not ack_ok:
        status = "Needs Review"
    else:
        status = "Passed"

    result = {
        "readiness_type": readiness_type,
        "status": status,
        "production_ready_allowed": int(production_ready_allowed),
        "required_ack": REQUIRED_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "risk_counts": {
            "open_critical_exception_alert_count": int(critical_alerts or 0),
            "open_high_exception_alert_count": int(high_alerts or 0),
            "overdue_critical_action_plan_count": int(overdue_critical_plans or 0),
            "overdue_action_plan_count": int(overdue_any_plans or 0),
            "unmapped_payroll_line_count": int(unmapped_payroll_lines or 0),
            "open_high_critical_leakage_count": int(open_leakage_count or 0),
            "unsafe_accounting_hook_count": int(unsafe_hook_count or 0),
            "fixture_warning_count": int(fixture_warning_count or 0),
        },
        "accounting_guardrails": {
            "payment_entry_count_today": int(guardrail_counts.get("Payment Entry") or 0),
            "journal_entry_count_today": int(guardrail_counts.get("Journal Entry") or 0),
            "gl_entry_count_today": int(guardrail_counts.get("GL Entry") or 0),
        },
        "latest_governance_pack": latest_pack,
        "items": items,
        "note": "Production readiness check only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }
    if int(dry_run or 0):
        result["dry_run"] = True
        return result

    doc = frappe.new_doc("NDIS Finance Production Readiness Check")
    doc.check_id = make_check_id(readiness_type)
    doc.readiness_type = readiness_type
    doc.status = status
    doc.site_name = frappe.local.site
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.production_ready_allowed = int(production_ready_allowed)
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]
    doc.open_critical_exception_alert_count = int(critical_alerts or 0)
    doc.open_high_exception_alert_count = int(high_alerts or 0)
    doc.overdue_critical_action_plan_count = int(overdue_critical_plans or 0)
    doc.unmapped_payroll_line_count = int(unmapped_payroll_lines or 0)
    doc.open_high_critical_leakage_count = int(open_leakage_count or 0)
    doc.unsafe_accounting_hook_count = int(unsafe_hook_count or 0)
    doc.payment_entry_count_today = int(guardrail_counts.get("Payment Entry") or 0)
    doc.journal_entry_count_today = int(guardrail_counts.get("Journal Entry") or 0)
    doc.gl_entry_count_today = int(guardrail_counts.get("GL Entry") or 0)
    doc.strict_accounting_guardrail = int(strict_accounting_guardrail or 0)
    doc.required_ack = REQUIRED_ACK
    doc.acknowledgement = acknowledgement
    if ack_ok:
        doc.acknowledged_on = now_datetime()
        doc.acknowledged_by = frappe.session.user
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc("NDIS Finance Production Readiness Check Item")
        row.readiness_check = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)

    frappe.db.commit()
    result["created"] = True
    result["readiness_check"] = doc.name
    result["check_id"] = doc.check_id
    return result


@frappe.whitelist()
def acknowledge_production_readiness(readiness_check, acknowledgement):
    assert_action("acknowledge_production_readiness")
    if not frappe.db.exists("NDIS Finance Production Readiness Check", readiness_check):
        frappe.throw(_("Readiness Check not found: {0}").format(readiness_check))

    doc = frappe.get_doc("NDIS Finance Production Readiness Check", readiness_check)
    if doc.status == "Cancelled":
        frappe.throw(_("Cancelled readiness checks cannot be acknowledged."))
    if acknowledgement != REQUIRED_ACK:
        frappe.throw(_("Invalid acknowledgement. Required: {0}").format(REQUIRED_ACK))
    if int(doc.blocker_count or 0):
        frappe.throw(_("Cannot allow production readiness while blockers exist."))

    new_status = "Passed" if int(doc.warning_count or 0) == 0 else "Needs Review"
    frappe.db.set_value(
        "NDIS Finance Production Readiness Check",
        readiness_check,
        {
            "acknowledgement": acknowledgement,
            "acknowledged_on": now_datetime(),
            "acknowledged_by": frappe.session.user,
            "production_ready_allowed": 1,
            "status": new_status,
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "readiness_check": readiness_check,
        "production_ready_allowed": 1,
        "status": new_status,
        "note": "Readiness acknowledged internally only. No accounting integration or posting was enabled.",
    }


@frappe.whitelist()
def cancel_production_readiness_check(readiness_check, reason=None):
    assert_action("cancel_production_readiness_check")
    if not frappe.db.exists("NDIS Finance Production Readiness Check", readiness_check):
        frappe.throw(_("Readiness Check not found: {0}").format(readiness_check))

    frappe.db.set_value(
        "NDIS Finance Production Readiness Check",
        readiness_check,
        {
            "status": "Cancelled",
            "production_ready_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Readiness check cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Finance Production Readiness Check Item`
        SET status = 'Cancelled'
        WHERE readiness_check = %(readiness_check)s
        """,
        {"readiness_check": readiness_check},
    )
    frappe.db.commit()
    return {
        "readiness_check": readiness_check,
        "status": "Cancelled",
        "note": "Readiness check cancelled only. No underlying finance/payroll/accounting records were changed.",
    }


@frappe.whitelist()
def quick_production_readiness_summary(limit=20):
    checks = frappe.get_all(
        "NDIS Finance Production Readiness Check",
        fields=[
            "name",
            "check_id",
            "readiness_type",
            "status",
            "site_name",
            "checked_on",
            "checked_by",
            "production_ready_allowed",
            "blocker_count",
            "warning_count",
            "pass_count",
            "item_count",
            "open_critical_exception_alert_count",
            "overdue_critical_action_plan_count",
            "unmapped_payroll_line_count",
            "unsafe_accounting_hook_count",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Finance Production Readiness Check Item",
        fields=[
            "name",
            "readiness_check",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "recommendation",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "checks": checks,
        "items": items,
        "required_ack": REQUIRED_ACK,
        "note": "Production readiness summary only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def execute_production_readiness_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key in ["status"]:
        if filters.get(key):
            conditions.append(f"{key} = %({key})s")
            params[key] = filters.get(key)
    if filters.get("from_date"):
        conditions.append("checked_on >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    if filters.get("production_ready_allowed") not in [None, ""]:
        conditions.append("production_ready_allowed = %(production_ready_allowed)s")
        params["production_ready_allowed"] = int(filters.get("production_ready_allowed"))

    columns = [
        {"fieldname": "readiness_check", "label": _("Readiness Check"), "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check", "width": 220},
        {"fieldname": "check_id", "label": _("Check ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "readiness_type", "label": _("Readiness Type"), "fieldtype": "Data", "width": 190},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "site_name", "label": _("Site"), "fieldtype": "Data", "width": 150},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "checked_by", "label": _("Checked By"), "fieldtype": "Link", "options": "User", "width": 160},
        {"fieldname": "production_ready_allowed", "label": _("Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 100},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 100},
        {"fieldname": "pass_count", "label": _("Pass"), "fieldtype": "Int", "width": 80},
        {"fieldname": "item_count", "label": _("Items"), "fieldtype": "Int", "width": 80},
        {"fieldname": "open_critical_exception_alert_count", "label": _("Critical Alerts"), "fieldtype": "Int", "width": 130},
        {"fieldname": "overdue_critical_action_plan_count", "label": _("Critical Overdue Plans"), "fieldtype": "Int", "width": 160},
        {"fieldname": "unmapped_payroll_line_count", "label": _("Unmapped Payroll"), "fieldtype": "Int", "width": 140},
        {"fieldname": "unsafe_accounting_hook_count", "label": _("Unsafe Hooks"), "fieldtype": "Int", "width": 120},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            name AS readiness_check,
            check_id,
            readiness_type,
            status,
            site_name,
            checked_on,
            checked_by,
            production_ready_allowed,
            blocker_count,
            warning_count,
            pass_count,
            item_count,
            open_critical_exception_alert_count,
            overdue_critical_action_plan_count,
            unmapped_payroll_line_count,
            unsafe_accounting_hook_count
        FROM `tabNDIS Finance Production Readiness Check`
        {build_where(conditions)}
        ORDER BY creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.check_id for row in data[:20]],
            "datasets": [
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
                {"name": "Pass", "values": [int(row.pass_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Checks"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.production_ready_allowed]), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": data[0].blocker_count if data else 0, "indicator": "Red" if data and int(data[0].blocker_count or 0) else "Green", "label": _("Latest Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_readiness_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for key in ["readiness_check", "status", "severity", "category"]:
        if filters.get(key):
            conditions.append(f"i.{key} = %({key})s")
            params[key] = filters.get(key)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check Item", "width": 220},
        {"fieldname": "readiness_check", "label": _("Readiness Check"), "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 280},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.readiness_check,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.recommendation,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Finance Production Readiness Check Item` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Info' THEN 3
                WHEN 'Pass' THEN 4
                ELSE 5
            END,
            i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Items", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
