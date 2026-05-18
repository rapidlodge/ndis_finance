import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE


REPORTS = [
    {
        "report_name": "NDIS Payroll Cost Import Reconciliation Report",
        "ref_doctype": "NDIS Payroll Cost Import",
    },
    {
        "report_name": "NDIS Payroll Cost by House Report",
        "ref_doctype": "NDIS Payroll Cost Import Line",
    },
    {
        "report_name": "NDIS Payroll Cost by Participant Report",
        "ref_doctype": "NDIS Cost Allocation Entry",
    },
    {
        "report_name": "NDIS Payroll Profitability Impact Report",
        "ref_doctype": "NDIS Cost Allocation Entry",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Payroll Cost Reconciliation",
        "type": "Report",
        "link_to": "NDIS Payroll Cost Import Reconciliation Report",
    },
    {
        "label": "Payroll Cost by House",
        "type": "Report",
        "link_to": "NDIS Payroll Cost by House Report",
    },
    {
        "label": "Payroll Cost by Participant",
        "type": "Report",
        "link_to": "NDIS Payroll Cost by Participant Report",
    },
    {
        "label": "Payroll Profitability Impact",
        "type": "Report",
        "link_to": "NDIS Payroll Profitability Impact Report",
    },
]

REPORT_FILE_MAP = {
    "NDIS Payroll Cost Import Reconciliation Report": "ndis_payroll_cost_import_reconciliation_report",
    "NDIS Payroll Cost by House Report": "ndis_payroll_cost_by_house_report",
    "NDIS Payroll Cost by Participant Report": "ndis_payroll_cost_by_participant_report",
    "NDIS Payroll Profitability Impact Report": "ndis_payroll_profitability_impact_report",
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_reports()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Payroll Cost Import",
        "NDIS Payroll Cost Import Line",
        "NDIS Cost Pool",
        "NDIS Cost Allocation Entry",
        "AU Payroll Run Log",
        "Employee",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 1U requires Phase 1T and AU Payroll. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    existing = frappe.db.exists("Report", report_name)

    if existing:
        doc = frappe.get_doc("Report", existing)
    else:
        doc = frappe.new_doc("Report")
        doc.report_name = report_name

    doc.ref_doctype = ref_doctype
    doc.report_type = "Script Report"
    doc.module = MODULE
    doc.is_standard = "Yes"
    doc.disabled = 0

    doc.roles = []
    for role in REPORT_ROLES:
        if frappe.db.exists("Role", role):
            doc.append("roles", {"role": role})

    doc.save(ignore_permissions=True)


def add_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )

    if not ws_name:
        return

    ws = frappe.get_doc("Workspace", ws_name)
    add_shortcuts_to_content_json(ws)
    add_shortcuts_to_child_table(ws)
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return

    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []

    text_blob = json.dumps(content)
    if "Payroll Profitability" not in text_blob:
        content.append(
            {
                "id": "ndis_payroll_profitability_heading",
                "type": "header",
                "data": {"text": "Payroll Profitability", "col": 12},
            }
        )

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue

        content.append(
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {
                    "label": shortcut["label"],
                    "link_to": shortcut["link_to"],
                    "type": shortcut["type"],
                    "col": 3,
                },
            }
        )

    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        row_type = "Report" if fieldname == "shortcuts" else "Link"
        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", ""))
            existing_blob += " " + str(getattr(row, "link_to", ""))

        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue

            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", row_type)
            set_child_value(row, "link_type", "Report")
            set_child_value(row, "report_ref_doctype", report_ref_doctype(shortcut["link_to"]))
            set_child_value(row, "is_query_report", 1)
            set_child_value(row, "open_in_new_tab", 0)


def report_ref_doctype(report_name):
    for report in REPORTS:
        if report["report_name"] == report_name:
            return report["ref_doctype"]
    return None


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    reports = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    report_details = {}
    for report in REPORTS:
        if frappe.db.exists("Report", report["report_name"]):
            doc = frappe.get_doc("Report", report["report_name"])
            report_details[report["report_name"]] = {
                "report_type": doc.report_type,
                "module": doc.module,
                "is_standard": doc.is_standard,
                "ref_doctype": doc.ref_doctype,
                "roles": [row.role for row in doc.roles],
            }

    return {
        "reports": reports,
        "report_details": report_details,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "report_files": report_files_exist(),
    }


def can_import_service():
    try:
        from ndis_finance.services.payroll_profitability_reporting import (
            quick_payroll_profitability_summary,
        )

        return callable(quick_payroll_profitability_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}

    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", "") or ""

    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        for row in getattr(ws, fieldname, []) or []:
            text_blob += " " + str(getattr(row, "label", ""))
            text_blob += " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result


def report_files_exist():
    app_path = frappe.get_app_path("ndis_finance")
    base_path = os.path.join(app_path, "ndis_finance", "report")
    result = {}

    for report_name, folder in REPORT_FILE_MAP.items():
        report_path = os.path.join(base_path, folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(report_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(report_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(report_path, "__init__.py")),
        }

    return result
