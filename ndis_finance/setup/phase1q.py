import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE


REPORTS = [
    {
        "report_name": "NDIS Funding Leakage Analytics Report",
        "ref_doctype": "NDIS Funding Leakage Register",
    },
    {
        "report_name": "NDIS Claim Cycle Time Report",
        "ref_doctype": "NDIS Claim Line",
    },
    {
        "report_name": "NDIS House Profitability Foundation Report",
        "ref_doctype": "NDIS Claim Line",
    },
    {
        "report_name": "NDIS Participant Profitability Foundation Report",
        "ref_doctype": "NDIS Claim Line",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Claims Officer",
    "NDIS Recovery Officer",
    "NDIS Finance Read Only",
]

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Leakage Analytics",
        "type": "Report",
        "link_to": "NDIS Funding Leakage Analytics Report",
    },
    {
        "label": "Claim Cycle Time",
        "type": "Report",
        "link_to": "NDIS Claim Cycle Time Report",
    },
    {
        "label": "House Profitability Foundation",
        "type": "Report",
        "link_to": "NDIS House Profitability Foundation Report",
    },
    {
        "label": "Participant Profitability Foundation",
        "type": "Report",
        "link_to": "NDIS Participant Profitability Foundation Report",
    },
]

REPORT_FILE_MAP = {
    "NDIS Funding Leakage Analytics Report": "ndis_funding_leakage_analytics_report",
    "NDIS Claim Cycle Time Report": "ndis_claim_cycle_time_report",
    "NDIS House Profitability Foundation Report": "ndis_house_profitability_foundation_report",
    "NDIS Participant Profitability Foundation Report": "ndis_participant_profitability_foundation_report",
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
        "NDIS Funding Leakage Register",
        "NDIS Claim Line",
        "NDIS Claim Batch",
        "NDIS Claim Export",
        "NDIS Remittance Import",
        "NDIS Recovery Case",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1Q requires previous phases. Missing DocTypes: {0}").format(
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

    if "CFO Analytics" not in text_blob:
        content.append(
            {
                "id": "ndis_cfo_analytics_heading",
                "type": "header",
                "data": {
                    "text": "CFO Analytics",
                    "col": 12,
                },
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
            existing_blob += (
                " "
                + str(getattr(row, "label", ""))
                + " "
                + str(getattr(row, "link_to", ""))
            )

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
        from ndis_finance.services.finance_analytics import quick_finance_analytics_summary

        return callable(quick_finance_analytics_summary)
    except Exception:
        return False


def report_files_exist():
    result = {}
    app_path = frappe.get_app_path("ndis_finance")
    for report_name, folder in REPORT_FILE_MAP.items():
        base_path = os.path.join(app_path, "ndis_finance", "report", folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(base_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(base_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(base_path, "__init__.py")),
        }
    return result


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )

    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}

    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)

    text_blob = ""
    if getattr(ws, "content", None):
        text_blob += ws.content

    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += (
                    " "
                    + str(getattr(row, "label", ""))
                    + " "
                    + str(getattr(row, "link_to", ""))
                )

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result
