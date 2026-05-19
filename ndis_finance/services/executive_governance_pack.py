import csv
import io
from html import escape

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today
from frappe.utils.file_manager import save_file

from ndis_finance.services.permissions import assert_action


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_pack_id(pack_type="Manual", pack_date=None):
    pack_date = pack_date or today()
    safe_type = frappe.scrub(pack_type or "Manual").replace("_", "-").upper()
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOV-PACK-{safe_type}-{pack_date}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def get_latest_snapshot():
    row = frappe.get_all(
        "NDIS Executive Dashboard Snapshot",
        filters={"status": "Active"},
        fields=["name"],
        order_by="snapshot_date desc, creation desc",
        limit=1,
    )
    return row[0].name if row else None


def get_snapshot(snapshot=None):
    snapshot = snapshot or get_latest_snapshot()
    if not snapshot:
        frappe.throw(_("No active executive dashboard snapshot found. Create a snapshot first."))
    return frappe.get_doc("NDIS Executive Dashboard Snapshot", snapshot)


def risk_status_for_pack(score):
    score = flt(score)
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Watch"
    if score >= 50:
        return "Needs Attention"
    return "Critical"


def calculate_governance_score(
    open_alerts,
    critical_alerts,
    high_alerts,
    overdue_plans,
    unmapped_payroll_lines,
    failed_automation_runs,
):
    score = 100
    score -= int(open_alerts or 0) * 3
    score -= int(critical_alerts or 0) * 15
    score -= int(high_alerts or 0) * 8
    score -= int(overdue_plans or 0) * 10
    score -= int(unmapped_payroll_lines or 0) * 5
    score -= int(failed_automation_runs or 0) * 10
    return round(max(score, 0), 2)


def add_item(
    items,
    section,
    title,
    risk_status="Info",
    amount=0,
    count_value=None,
    percent_value=None,
    source_doctype=None,
    source_name=None,
    source_reference=None,
    note=None,
):
    items.append(
        {
            "section": section,
            "display_order": len(items) + 1,
            "title": title,
            "risk_status": risk_status,
            "amount": flt(amount),
            "count_value": count_value,
            "percent_value": percent_value,
            "source_doctype": source_doctype,
            "source_name": source_name,
            "source_reference": source_reference,
            "note": note,
        }
    )


def build_pack_items(snapshot_doc, include_resolved_items=0, trend_limit=6):
    items = []

    add_item(
        items,
        "Executive KPI",
        "Paid Revenue",
        "Good",
        snapshot_doc.paid_revenue,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Paid revenue from latest executive snapshot.",
    )
    add_item(
        items,
        "Executive KPI",
        "Total Allocated Cost",
        "Info",
        snapshot_doc.total_allocated_cost,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Total management cost allocation.",
    )
    add_item(
        items,
        "Executive KPI",
        "Payroll Cost",
        "Info",
        snapshot_doc.payroll_cost,
        percent_value=snapshot_doc.payroll_cost_ratio,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Payroll cost imported through the NDIS payroll costing bridge.",
    )
    add_item(
        items,
        "Executive KPI",
        "Estimated Margin",
        "Good" if flt(snapshot_doc.estimated_margin) >= 0 else "Risk",
        snapshot_doc.estimated_margin,
        percent_value=snapshot_doc.estimated_margin_percent,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Paid revenue less allocated cost.",
    )
    add_item(
        items,
        "Executive KPI",
        "Open Leakage",
        "Risk" if flt(snapshot_doc.open_leakage_amount) else "Good",
        snapshot_doc.open_leakage_amount,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Open or in-review funding leakage amount.",
    )
    add_item(
        items,
        "Executive KPI",
        "Open Recovery",
        "Watch" if flt(snapshot_doc.open_recovery_amount) else "Good",
        snapshot_doc.open_recovery_amount,
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Open recovery pipeline.",
    )
    add_item(
        items,
        "Executive KPI",
        "Unmapped Payroll Lines",
        "Risk" if int(snapshot_doc.unmapped_payroll_lines or 0) else "Good",
        count_value=int(snapshot_doc.unmapped_payroll_lines or 0),
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Payroll rows without NDIS costing mapping.",
    )
    add_item(
        items,
        "Executive KPI",
        "Failed Automation Runs 7 Days",
        "Risk" if int(snapshot_doc.failed_automation_runs_7_days or 0) else "Good",
        count_value=int(snapshot_doc.failed_automation_runs_7_days or 0),
        source_doctype="NDIS Executive Dashboard Snapshot",
        source_name=snapshot_doc.name,
        source_reference=snapshot_doc.snapshot_id,
        note="Failed scheduled automation runs in the last 7 days.",
    )

    alert_status_filter = ["!=", "Cancelled"] if int(include_resolved_items or 0) else ["in", ["Open", "In Review"]]
    alerts = frappe.get_all(
        "NDIS Executive Exception Alert",
        filters={"status": alert_status_filter},
        fields=[
            "name",
            "alert_id",
            "status",
            "severity",
            "rule_name",
            "metric_label",
            "metric_value",
            "operator",
            "threshold_value",
            "recommendation",
        ],
        order_by="creation desc",
        limit=50,
    )
    for alert in alerts:
        add_item(
            items,
            "Exception Alerts",
            alert.rule_name,
            "Critical" if alert.severity == "Critical" else "Risk" if alert.severity in ["High", "Medium"] else "Watch",
            source_doctype="NDIS Executive Exception Alert",
            source_name=alert.name,
            source_reference=alert.alert_id,
            note=(
                f"{alert.metric_label}: {alert.metric_value} {alert.operator} {alert.threshold_value}. "
                f"Status: {alert.status}. Recommendation: {alert.recommendation or ''}"
            ),
        )

    plan_status_filter = ["not in", ["Cancelled"]] if int(include_resolved_items or 0) else ["not in", ["Completed", "Cancelled"]]
    plans = frappe.get_all(
        "NDIS Executive Exception Action Plan",
        filters={"status": plan_status_filter},
        fields=[
            "name",
            "action_plan_id",
            "status",
            "priority",
            "assigned_to",
            "due_date",
            "total_steps",
            "completed_steps",
            "open_steps",
            "overdue_steps",
            "management_sign_off",
            "action_title",
        ],
        order_by="modified desc",
        limit=50,
    )
    for plan in plans:
        risk = "Critical" if plan.priority == "Critical" else "Risk" if plan.status in ["Overdue", "Escalated"] else "Watch" if plan.status == "In Progress" else "Good"
        add_item(
            items,
            "Action Plans",
            plan.action_title,
            risk,
            count_value=int(plan.open_steps or 0),
            source_doctype="NDIS Executive Exception Action Plan",
            source_name=plan.name,
            source_reference=plan.action_plan_id,
            note=(
                f"Status: {plan.status}. Owner: {plan.assigned_to or 'Unassigned'}. "
                f"Due: {plan.due_date or 'Not set'}. Steps: {plan.completed_steps}/{plan.total_steps}. "
                f"Overdue steps: {plan.overdue_steps}. Sign-off: {bool(plan.management_sign_off)}."
            ),
        )

    trend_snapshots = frappe.get_all(
        "NDIS Executive Dashboard Snapshot",
        filters={"status": "Active"},
        fields=[
            "name",
            "snapshot_id",
            "snapshot_date",
            "paid_revenue",
            "total_allocated_cost",
            "payroll_cost",
            "estimated_margin",
            "estimated_margin_percent",
            "open_leakage_amount",
            "open_recovery_amount",
        ],
        order_by="snapshot_date desc, creation desc",
        limit=int(trend_limit or 6),
    )
    for snap in reversed(trend_snapshots):
        add_item(
            items,
            "Trend Summary",
            f"Snapshot {snap.snapshot_date}",
            "Good" if flt(snap.estimated_margin) >= 0 else "Risk",
            snap.estimated_margin,
            percent_value=snap.estimated_margin_percent,
            source_doctype="NDIS Executive Dashboard Snapshot",
            source_name=snap.name,
            source_reference=snap.snapshot_id,
            note=(
                f"Paid revenue {flt(snap.paid_revenue):.2f}; allocated cost {flt(snap.total_allocated_cost):.2f}; "
                f"payroll cost {flt(snap.payroll_cost):.2f}; open leakage {flt(snap.open_leakage_amount):.2f}; "
                f"open recovery {flt(snap.open_recovery_amount):.2f}."
            ),
        )

    return items


def summarise_items(items):
    open_alerts = len([item for item in items if item["section"] == "Exception Alerts" and item["risk_status"] in ["Risk", "Critical"]])
    critical_alerts = len([item for item in items if item["section"] == "Exception Alerts" and item["risk_status"] == "Critical"])
    high_alerts = len([item for item in items if item["section"] == "Exception Alerts" and item["risk_status"] == "Risk"])
    open_action_plans = len([item for item in items if item["section"] == "Action Plans" and item["risk_status"] in ["Watch", "Risk", "Critical"]])
    overdue_action_plans = len([item for item in items if item["section"] == "Action Plans" and item["risk_status"] in ["Risk", "Critical"]])
    signed_off_action_plans = frappe.db.count(
        "NDIS Executive Exception Action Plan",
        {"management_sign_off": 1, "status": "Completed"},
    )
    return {
        "open_alerts": open_alerts,
        "critical_alerts": critical_alerts,
        "high_alerts": high_alerts,
        "open_action_plans": open_action_plans,
        "overdue_action_plans": overdue_action_plans,
        "signed_off_action_plans": signed_off_action_plans,
    }


@frappe.whitelist()
def create_governance_pack(
    pack_type="Manual",
    pack_date=None,
    snapshot=None,
    include_resolved_items=0,
    replace_existing=0,
    dry_run=0,
    notes=None,
):
    assert_action("create_governance_pack")

    pack_date = pack_date or today()
    snapshot_doc = get_snapshot(snapshot)
    items = build_pack_items(snapshot_doc, include_resolved_items=include_resolved_items)
    item_summary = summarise_items(items)
    score = calculate_governance_score(
        open_alerts=item_summary["open_alerts"],
        critical_alerts=item_summary["critical_alerts"],
        high_alerts=item_summary["high_alerts"],
        overdue_plans=item_summary["overdue_action_plans"],
        unmapped_payroll_lines=snapshot_doc.unmapped_payroll_lines,
        failed_automation_runs=snapshot_doc.failed_automation_runs_7_days,
    )
    governance_status = risk_status_for_pack(score)

    if int(dry_run or 0):
        return {
            "dry_run": True,
            "pack_type": pack_type,
            "pack_date": pack_date,
            "snapshot": snapshot_doc.name,
            "item_count": len(items),
            "governance_score": score,
            "governance_status": governance_status,
            "preview_items": items[:15],
            "note": "Dry run only. No governance pack, files, or items created.",
        }

    existing = frappe.get_all(
        "NDIS Executive Governance Pack",
        filters={
            "pack_date": pack_date,
            "pack_type": pack_type,
            "source_snapshot": snapshot_doc.name,
            "status": ["!=", "Cancelled"],
        },
        fields=["name"],
        limit=1,
    )
    if existing and not int(replace_existing or 0):
        return {
            "created": False,
            "duplicate": True,
            "governance_pack": existing[0].name,
            "message": "Active governance pack already exists for this date/type/source snapshot.",
        }
    if existing and int(replace_existing or 0):
        for row in existing:
            cancel_governance_pack(
                governance_pack=row.name,
                reason="Cancelled by replace_existing governance pack creation.",
                ignore_permissions=True,
            )

    pack = frappe.new_doc("NDIS Executive Governance Pack")
    pack.pack_id = make_pack_id(pack_type, pack_date)
    pack.pack_date = pack_date
    pack.pack_type = pack_type
    pack.status = "Generated"
    pack.period_start = snapshot_doc.period_start
    pack.period_end = snapshot_doc.period_end
    pack.source_snapshot = snapshot_doc.name
    pack.snapshot_date = snapshot_doc.snapshot_date
    pack.include_resolved_items = int(include_resolved_items or 0)
    pack.paid_revenue = flt(snapshot_doc.paid_revenue)
    pack.total_allocated_cost = flt(snapshot_doc.total_allocated_cost)
    pack.payroll_cost = flt(snapshot_doc.payroll_cost)
    pack.estimated_margin = flt(snapshot_doc.estimated_margin)
    pack.estimated_margin_percent = flt(snapshot_doc.estimated_margin_percent)
    pack.open_leakage_amount = flt(snapshot_doc.open_leakage_amount)
    pack.open_recovery_amount = flt(snapshot_doc.open_recovery_amount)
    pack.open_exception_alert_count = item_summary["open_alerts"]
    pack.critical_exception_count = item_summary["critical_alerts"]
    pack.high_exception_count = item_summary["high_alerts"]
    pack.open_action_plan_count = item_summary["open_action_plans"]
    pack.overdue_action_plan_count = item_summary["overdue_action_plans"]
    pack.signed_off_action_plan_count = item_summary["signed_off_action_plans"]
    pack.item_count = len(items)
    pack.governance_score = score
    pack.governance_status = governance_status
    pack.generated_on = now_datetime()
    pack.generated_by = frappe.session.user
    pack.notes = notes
    pack.insert(ignore_permissions=True)

    created_items = []
    for item in items:
        row = frappe.new_doc("NDIS Executive Governance Pack Item")
        row.governance_pack = pack.name
        row.pack_date = pack_date
        row.status = "Active"
        row.section = item["section"]
        row.display_order = item["display_order"]
        row.title = item["title"]
        row.risk_status = item["risk_status"]
        row.amount = flt(item.get("amount"))
        row.count_value = item.get("count_value")
        row.percent_value = item.get("percent_value")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.source_reference = item.get("source_reference")
        row.note = item.get("note")
        row.insert(ignore_permissions=True)
        created_items.append(row.name)

    html_file, csv_file = create_pack_exports(pack.name)
    frappe.db.set_value(
        "NDIS Executive Governance Pack",
        pack.name,
        {"board_pack_html_file": html_file, "board_pack_csv_file": csv_file},
        update_modified=False,
    )
    frappe.db.commit()

    return {
        "created": True,
        "governance_pack": pack.name,
        "pack_id": pack.pack_id,
        "item_count": len(created_items),
        "governance_score": score,
        "governance_status": governance_status,
        "board_pack_html_file": html_file,
        "board_pack_csv_file": csv_file,
        "note": "Governance pack generated for internal board reporting only. No accounting, payroll, STP, ABA, email, or payment movement created.",
    }


def create_pack_exports(governance_pack):
    pack = frappe.get_doc("NDIS Executive Governance Pack", governance_pack)
    items = frappe.get_all(
        "NDIS Executive Governance Pack Item",
        filters={"governance_pack": governance_pack, "status": "Active"},
        fields=[
            "section",
            "display_order",
            "title",
            "risk_status",
            "amount",
            "count_value",
            "percent_value",
            "source_doctype",
            "source_name",
            "source_reference",
            "note",
        ],
        order_by="display_order asc",
    )

    html_doc = save_file(
        fname=f"{pack.pack_id}.html",
        content=build_html(pack, items).encode("utf-8"),
        dt="NDIS Executive Governance Pack",
        dn=pack.name,
        is_private=1,
    )
    csv_doc = save_file(
        fname=f"{pack.pack_id}.csv",
        content=build_csv(items).encode("utf-8"),
        dt="NDIS Executive Governance Pack",
        dn=pack.name,
        is_private=1,
    )
    return html_doc.file_url, csv_doc.file_url


def fmt_amount(value):
    return f"{currency()} {flt(value):,.2f}"


def fmt_percent(value):
    return f"{flt(value):.2f}%"


def build_html(pack, items):
    rows_html = []
    current_section = None
    for item in items:
        if item.section != current_section:
            current_section = item.section
            rows_html.append(f"<tr class='section'><td colspan='6'>{escape(current_section or '')}</td></tr>")
        rows_html.append(
            "<tr>"
            f"<td>{escape(item.title or '')}</td>"
            f"<td>{escape(item.risk_status or '')}</td>"
            f"<td>{fmt_amount(item.amount)}</td>"
            f"<td>{'' if item.count_value is None else int(item.count_value)}</td>"
            f"<td>{fmt_percent(item.percent_value)}</td>"
            f"<td>{escape(item.note or '')}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(pack.pack_id)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 28px; color: #222; }}
h1 {{ margin-bottom: 4px; }}
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
.card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; }}
.card .label {{ color: #666; font-size: 12px; }}
.card .value {{ font-size: 20px; font-weight: bold; margin-top: 6px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; font-size: 12px; }}
th {{ background: #f4f4f4; }}
tr.section td {{ background: #222; color: white; font-weight: bold; font-size: 14px; }}
.footer {{ margin-top: 24px; font-size: 12px; color: #666; }}
</style>
</head>
<body>
<h1>NDIS Executive Governance Pack</h1>
<p><strong>Pack ID:</strong> {escape(pack.pack_id)}<br>
<strong>Pack Date:</strong> {escape(str(pack.pack_date))}<br>
<strong>Status:</strong> {escape(pack.status)}<br>
<strong>Governance Status:</strong> {escape(pack.governance_status or '')}<br>
<strong>Source Snapshot:</strong> {escape(pack.source_snapshot or '')}</p>

<div class="summary">
    <div class="card"><div class="label">Paid Revenue</div><div class="value">{fmt_amount(pack.paid_revenue)}</div></div>
    <div class="card"><div class="label">Allocated Cost</div><div class="value">{fmt_amount(pack.total_allocated_cost)}</div></div>
    <div class="card"><div class="label">Estimated Margin</div><div class="value">{fmt_amount(pack.estimated_margin)}</div></div>
    <div class="card"><div class="label">Margin %</div><div class="value">{fmt_percent(pack.estimated_margin_percent)}</div></div>
    <div class="card"><div class="label">Open Exceptions</div><div class="value">{int(pack.open_exception_alert_count or 0)}</div></div>
    <div class="card"><div class="label">Overdue Actions</div><div class="value">{int(pack.overdue_action_plan_count or 0)}</div></div>
    <div class="card"><div class="label">Open Leakage</div><div class="value">{fmt_amount(pack.open_leakage_amount)}</div></div>
    <div class="card"><div class="label">Governance Score</div><div class="value">{fmt_percent(pack.governance_score)}</div></div>
</div>

<table>
<thead><tr><th>Title</th><th>Risk</th><th>Amount</th><th>Count</th><th>Percent</th><th>Note</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>

<div class="footer">
Generated on {escape(str(pack.generated_on))} by {escape(pack.generated_by or '')}. This pack is for internal governance reporting only and does not create accounting, payroll, STP, ABA, email, or payment movement.
</div>
</body>
</html>"""


def build_csv(items):
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "section",
            "display_order",
            "title",
            "risk_status",
            "amount",
            "count_value",
            "percent_value",
            "source_doctype",
            "source_name",
            "source_reference",
            "note",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "section": item.section,
                "display_order": item.display_order,
                "title": item.title,
                "risk_status": item.risk_status,
                "amount": flt(item.amount),
                "count_value": item.count_value,
                "percent_value": flt(item.percent_value),
                "source_doctype": item.source_doctype,
                "source_name": item.source_name,
                "source_reference": item.source_reference,
                "note": item.note,
            }
        )
    return output.getvalue()


@frappe.whitelist()
def signoff_governance_pack(governance_pack, signoff_note=None):
    assert_action("signoff_governance_pack")
    if not frappe.db.exists("NDIS Executive Governance Pack", governance_pack):
        frappe.throw(_("Governance Pack not found: {0}").format(governance_pack))

    frappe.db.set_value(
        "NDIS Executive Governance Pack",
        governance_pack,
        {
            "status": "Signed Off",
            "management_sign_off": 1,
            "signed_off_by": frappe.session.user,
            "signed_off_on": now_datetime(),
            "signoff_note": signoff_note or "Signed off.",
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "governance_pack": governance_pack,
        "status": "Signed Off",
        "note": "Governance pack signed off internally only. No email, accounting, payroll, STP, ABA, or payment movement created.",
    }


@frappe.whitelist()
def cancel_governance_pack(governance_pack, reason=None, ignore_permissions=False):
    if not ignore_permissions:
        assert_action("cancel_governance_pack")
    if not frappe.db.exists("NDIS Executive Governance Pack", governance_pack):
        frappe.throw(_("Governance Pack not found: {0}").format(governance_pack))

    frappe.db.set_value(
        "NDIS Executive Governance Pack",
        governance_pack,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Governance pack cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Executive Governance Pack Item`
        SET status = 'Cancelled'
        WHERE governance_pack = %(governance_pack)s
        """,
        {"governance_pack": governance_pack},
    )
    frappe.db.commit()
    return {
        "governance_pack": governance_pack,
        "status": "Cancelled",
        "note": "Governance pack cancelled only. No underlying finance/payroll/accounting records were changed.",
    }


@frappe.whitelist()
def quick_governance_pack_summary(limit=20):
    packs = frappe.get_all(
        "NDIS Executive Governance Pack",
        fields=[
            "name",
            "pack_id",
            "pack_date",
            "pack_type",
            "status",
            "source_snapshot",
            "paid_revenue",
            "total_allocated_cost",
            "payroll_cost",
            "estimated_margin",
            "estimated_margin_percent",
            "open_exception_alert_count",
            "overdue_action_plan_count",
            "governance_score",
            "governance_status",
            "board_pack_html_file",
            "board_pack_csv_file",
            "management_sign_off",
        ],
        order_by="pack_date desc, creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Executive Governance Pack Item",
        fields=[
            "name",
            "governance_pack",
            "pack_date",
            "section",
            "title",
            "risk_status",
            "amount",
            "count_value",
            "percent_value",
            "source_doctype",
            "source_name",
        ],
        order_by="pack_date desc, display_order asc",
        limit=int(limit or 20),
    )
    return {
        "packs": packs,
        "items": items,
        "note": "Governance pack summary only. No finance, payroll, accounting, STP, ABA, email, or payment movement created.",
    }


def execute_governance_pack_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("from_date"):
        conditions.append("p.pack_date >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("p.pack_date <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("pack_type"):
        conditions.append("p.pack_type = %(pack_type)s")
        params["pack_type"] = filters.get("pack_type")
    if filters.get("governance_status"):
        conditions.append("p.governance_status = %(governance_status)s")
        params["governance_status"] = filters.get("governance_status")

    params["currency"] = currency()
    columns = [
        {"fieldname": "governance_pack", "label": _("Governance Pack"), "fieldtype": "Link", "options": "NDIS Executive Governance Pack", "width": 210},
        {"fieldname": "pack_id", "label": _("Pack ID"), "fieldtype": "Data", "width": 300},
        {"fieldname": "pack_date", "label": _("Pack Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "pack_type", "label": _("Pack Type"), "fieldtype": "Data", "width": 120},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "governance_status", "label": _("Governance Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "governance_score", "label": _("Governance Score"), "fieldtype": "Percent", "width": 140},
        {"fieldname": "paid_revenue", "label": _("Paid Revenue"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "total_allocated_cost", "label": _("Allocated Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "payroll_cost", "label": _("Payroll Cost"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "estimated_margin", "label": _("Margin"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "estimated_margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "open_exception_alert_count", "label": _("Open Exceptions"), "fieldtype": "Int", "width": 130},
        {"fieldname": "overdue_action_plan_count", "label": _("Overdue Actions"), "fieldtype": "Int", "width": 130},
        {"fieldname": "item_count", "label": _("Items"), "fieldtype": "Int", "width": 90},
        {"fieldname": "board_pack_html_file", "label": _("HTML File"), "fieldtype": "Data", "width": 260},
        {"fieldname": "board_pack_csv_file", "label": _("CSV File"), "fieldtype": "Data", "width": 260},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS governance_pack,
            p.pack_id,
            p.pack_date,
            p.pack_type,
            p.status,
            p.governance_status,
            p.governance_score,
            p.paid_revenue,
            p.total_allocated_cost,
            p.payroll_cost,
            p.estimated_margin,
            p.estimated_margin_percent,
            p.open_exception_alert_count,
            p.overdue_action_plan_count,
            p.item_count,
            p.board_pack_html_file,
            p.board_pack_csv_file,
            %(currency)s AS currency
        FROM `tabNDIS Executive Governance Pack` p
        {build_where(conditions)}
        ORDER BY p.pack_date DESC, p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [str(row.pack_date) for row in data],
            "datasets": [
                {"name": "Paid Revenue", "values": [flt(row.paid_revenue) for row in data]},
                {"name": "Allocated Cost", "values": [flt(row.total_allocated_cost) for row in data]},
                {"name": "Margin", "values": [flt(row.estimated_margin) for row in data]},
            ],
        },
        "type": "line",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Packs"), "datatype": "Int"},
        {"value": data[0].governance_score if data else 0, "indicator": "Green" if data and flt(data[0].governance_score) >= 85 else "Orange", "label": _("Latest Governance Score"), "datatype": "Percent"},
        {"value": data[0].estimated_margin if data else 0, "indicator": "Green" if data and flt(data[0].estimated_margin) >= 0 else "Red", "label": _("Latest Margin"), "datatype": "Currency", "currency": currency()},
        {"value": data[0].open_exception_alert_count if data else 0, "indicator": "Red" if data and int(data[0].open_exception_alert_count or 0) else "Green", "label": _("Latest Open Exceptions"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_governance_pack_detail_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = ["i.status = 'Active'"]
    params = {}

    if filters.get("governance_pack"):
        conditions.append("i.governance_pack = %(governance_pack)s")
        params["governance_pack"] = filters.get("governance_pack")
    if filters.get("section"):
        conditions.append("i.section = %(section)s")
        params["section"] = filters.get("section")
    if filters.get("risk_status"):
        conditions.append("i.risk_status = %(risk_status)s")
        params["risk_status"] = filters.get("risk_status")
    if filters.get("from_date"):
        conditions.append("i.pack_date >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("i.pack_date <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    params["currency"] = currency()
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Executive Governance Pack Item", "width": 210},
        {"fieldname": "governance_pack", "label": _("Governance Pack"), "fieldtype": "Link", "options": "NDIS Executive Governance Pack", "width": 210},
        {"fieldname": "pack_date", "label": _("Pack Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 160},
        {"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 280},
        {"fieldname": "risk_status", "label": _("Risk Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
        {"fieldname": "count_value", "label": _("Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "percent_value", "label": _("Percent"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "note", "label": _("Note"), "fieldtype": "Small Text", "width": 450},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.governance_pack,
            i.pack_date,
            i.section,
            i.title,
            i.risk_status,
            i.amount,
            i.count_value,
            i.percent_value,
            i.source_doctype,
            i.source_name,
            i.note,
            %(currency)s AS currency
        FROM `tabNDIS Executive Governance Pack Item` i
        WHERE {" AND ".join(conditions)}
        ORDER BY i.pack_date DESC, i.display_order ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.risk_status or "Info"
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
        {"value": len([row for row in data if row.risk_status in ["Risk", "Critical"]]), "indicator": "Red", "label": _("Risk/Critical"), "datatype": "Int"},
        {"value": len([row for row in data if row.risk_status == "Watch"]), "indicator": "Orange", "label": _("Watch"), "datatype": "Int"},
        {"value": len([row for row in data if row.risk_status == "Good"]), "indicator": "Green", "label": _("Good"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
