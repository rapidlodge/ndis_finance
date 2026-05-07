import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE


REPORTS = [
    {
        "report_name": "NDIS Automation Health Report",
        "ref_doctype": "NDIS Recovery Automation Log",
    },
    {
        "report_name": "NDIS Automation Exception Report",
        "ref_doctype": "NDIS Recovery Automation Log",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Recovery Officer",
]

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Automation Health",
        "type": "Report",
        "link_to": "NDIS Automation Health Report",
    },
    {
        "label": "Automation Exceptions",
        "type": "Report",
        "link_to": "NDIS Automation Exception Report",
    },
    {
        "label": "Automation Logs",
        "type": "DocType",
        "link_to": "NDIS Recovery Automation Log",
    },
]


@frappe.whitelist()
def install():
    validate_phase1k()
    create_reports()
    add_workspace_shortcuts()
    frappe.db.commit()
    return health_check()


def validate_phase1k():
    required = [
        "NDIS Recovery Automation Log",
        "NDIS Recovery Case",
        "NDIS Recovery Email Draft",
        "NDIS Funding Leakage Register",
        "NDIS Claim Line",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1L requires previous phases. Missing DocTypes: {0}").format(
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

    existing_labels = set()
    existing_text = set()
    shortcut_labels = {shortcut["label"] for shortcut in WORKSPACE_SHORTCUTS}

    for block in content:
        data = block.get("data") or {}
        if data.get("label"):
            existing_labels.add(data.get("label"))
            if data.get("label") in shortcut_labels:
                data.setdefault("shortcut_name", data.get("label"))
        if data.get("shortcut_name"):
            existing_labels.add(data.get("shortcut_name"))
        if data.get("text"):
            existing_text.add(data.get("text"))

    if "Automation Monitoring" not in existing_text:
        content.append(
            {
                "id": "ndis_automation_monitoring_heading",
                "type": "header",
                "data": {
                    "text": "Automation Monitoring",
                    "col": 12,
                },
            }
        )

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in existing_labels:
            continue

        content.append(
            {
                "id": frappe.scrub(shortcut["label"]),
                "type": "shortcut",
                "data": {
                    "shortcut_name": shortcut["label"],
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

        existing_labels = set()
        for row in getattr(ws, fieldname, []) or []:
            if getattr(row, "label", None):
                existing_labels.add(row.label)

        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_labels:
                continue

            row = ws.append(fieldname, {})
            row_type = shortcut["type"]
            if fieldname == "links":
                row_type = "Link"

            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", row_type)
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(
                row,
                "document_type",
                shortcut["link_to"] if shortcut["type"] == "DocType" else None,
            )
            set_child_value(
                row,
                "report_ref_doctype",
                "NDIS Recovery Automation Log" if shortcut["type"] == "Report" else None,
            )
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if value is None:
        return

    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    reports = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})

    return {
        "reports": reports,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "js_files": {
            "public/js/ndis_recovery_automation_log.js": file_exists(
                "public/js/ndis_recovery_automation_log.js"
            ),
            "public/js/ndis_recovery_automation_log_list.js": file_exists(
                "public/js/ndis_recovery_automation_log_list.js"
            ),
        },
        "doctype_js_hooks": {
            "NDIS Recovery Automation Log": "NDIS Recovery Automation Log" in doctype_js,
        },
        "doctype_list_js_hooks": {
            "NDIS Recovery Automation Log": "NDIS Recovery Automation Log" in doctype_list_js,
        },
    }


def can_import_service():
    try:
        from ndis_finance.services.automation_reporting import (
            quick_automation_dashboard_summary,
        )

        return callable(quick_automation_dashboard_summary)
    except Exception:
        return False


def file_exists(relative_path):
    app_path = frappe.get_app_path("ndis_finance")
    app_root = os.path.dirname(app_path)
    return os.path.exists(os.path.join(app_root, "ndis_finance", relative_path))


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
                text_blob += " " + str(getattr(row, "label", ""))
                text_blob += " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result
