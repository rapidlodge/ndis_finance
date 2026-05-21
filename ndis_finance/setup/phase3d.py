import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE3D_DOCTYPES = [
    "NDIS Sandbox Payment Entry Cleanup Run",
    "NDIS Sandbox Payment Entry Cleanup Line",
]

REPORTS = [
    {
        "report_name": "NDIS Sandbox Payment Entry Cleanup Report",
        "ref_doctype": "NDIS Sandbox Payment Entry Cleanup Run",
    },
    {
        "report_name": "NDIS Sandbox Payment Entry Hygiene Report",
        "ref_doctype": "Payment Entry",
    },
]

REPORT_FILE_MAP = {
    "NDIS Sandbox Payment Entry Cleanup Report": "ndis_sandbox_payment_entry_cleanup_report",
    "NDIS Sandbox Payment Entry Hygiene Report": "ndis_sandbox_payment_entry_hygiene_report",
}

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    "NDIS Sandbox Payment Entry Cleanup Run": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Sandbox Payment Entry Cleanup Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "Sandbox Payment Entry Cleanup Runs",
        "type": "DocType",
        "link_to": "NDIS Sandbox Payment Entry Cleanup Run",
    },
    {
        "label": "Sandbox Payment Entry Cleanup Lines",
        "type": "DocType",
        "link_to": "NDIS Sandbox Payment Entry Cleanup Line",
    },
    {
        "label": "Sandbox Payment Entry Cleanup Report",
        "type": "Report",
        "link_to": "NDIS Sandbox Payment Entry Cleanup Report",
    },
    {
        "label": "Sandbox Payment Entry Hygiene",
        "type": "Report",
        "link_to": "NDIS Sandbox Payment Entry Hygiene Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_cleanup_run_doctype()
    create_cleanup_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Sandbox Payment Entry Run",
        "NDIS Sandbox Payment Entry Run Line",
        "NDIS Payment Entry Allocation Preview",
        "Payment Entry",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(_("Phase 3D requires Phase 3C. Missing DocTypes: {0}").format(", ".join(missing)))

    required_fields = [
        "custom_ndis_sandbox_payment_entry_run",
        "custom_ndis_payment_entry_allocation_preview",
        "custom_ndis_sandbox_payment_entry_draft_only",
        "custom_ndis_sandbox_payment_entry_acknowledgement",
    ]

    missing_fields = [
        fieldname
        for fieldname in required_fields
        if not frappe.db.exists("Custom Field", {"dt": "Payment Entry", "fieldname": fieldname})
    ]

    if missing_fields:
        frappe.throw(
            _("Phase 3D requires Phase 3C Payment Entry custom fields. Missing: {0}").format(
                ", ".join(missing_fields)
            )
        )


def create_cleanup_run_doctype():
    _create_doctype(
        name="NDIS Sandbox Payment Entry Cleanup Run",
        autoname="field:cleanup_id",
        title_field="cleanup_id",
        fields=[
            {"fieldname": "cleanup_id", "label": "Cleanup ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nCleaned\nBlocked\nCancelled\nFailed", "default": "Draft", "in_list_view": 1},
            {"fieldname": "cleanup_mode", "label": "Cleanup Mode", "fieldtype": "Select", "options": "\nPreview Only\nDelete Draft Sandbox Payment Entry", "default": "Preview Only", "in_list_view": 1},
            {"fieldname": "target_section", "label": "Cleanup Target", "fieldtype": "Section Break"},
            {"fieldname": "target_sandbox_run", "label": "Target Sandbox Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run"},
            {"fieldname": "target_payment_entry", "label": "Target Payment Entry", "fieldtype": "Link", "options": "Payment Entry"},
            {"fieldname": "older_than_days", "label": "Older Than Days", "fieldtype": "Int", "default": "0"},
            {"fieldname": "include_cancelled_runs", "label": "Include Cancelled Runs", "fieldtype": "Check", "default": "1"},
            {"fieldname": "control_section", "label": "Safety Controls", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "candidate_count", "label": "Candidate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_count", "label": "Eligible Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_count", "label": "Blocked Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "deleted_payment_entry_count", "label": "Deleted Draft PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "linked_gl_entry_count", "label": "Linked GL Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_sandbox_pe_count", "label": "Submitted Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_cleanup_line_doctype():
    _create_doctype(
        name="NDIS Sandbox Payment Entry Cleanup Line",
        autoname="hash",
        title_field="payment_entry",
        fields=[
            {"fieldname": "cleanup_run", "label": "Cleanup Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Cleanup Run", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nCandidate\nEligible\nDeleted\nBlocked\nCancelled", "default": "Candidate", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "sandbox_run", "label": "Sandbox Run", "fieldtype": "Link", "options": "NDIS Sandbox Payment Entry Run"},
            {"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "payment_entry_exists_before", "label": "PE Exists Before", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_exists_after", "label": "PE Exists After", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_docstatus", "label": "PE Docstatus", "fieldtype": "Int"},
            {"fieldname": "sandbox_draft_only", "label": "Sandbox Draft Only", "fieldtype": "Check"},
            {"fieldname": "linked_gl_entry_count", "label": "Linked GL Entry Count", "fieldtype": "Int"},
            {"fieldname": "age_days", "label": "Age Days", "fieldtype": "Int"},
            {"fieldname": "allocation_preview", "label": "Allocation Preview", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview"},
            {"fieldname": "party", "label": "Party", "fieldtype": "Data"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Currency"},
            {"fieldname": "received_amount", "label": "Received Amount", "fieldtype": "Currency"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "action_taken", "label": "Action Taken", "fieldtype": "Small Text"},
        ],
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


def harden_permissions():
    for doctype, role_map in DOC_PERM_MATRIX.items():
        if not frappe.db.exists("DocType", doctype):
            continue

        doc = frappe.get_doc("DocType", doctype)
        doc.permissions = []

        for role, profile in role_map.items():
            if frappe.db.exists("Role", role):
                doc.append("permissions", build_perm_row(role, profile))

        doc.save(ignore_permissions=True)
        frappe.clear_cache(doctype=doctype)


def build_perm_row(role, profile):
    base = {
        "role": role,
        "permlevel": 0,
        "read": 0,
        "write": 0,
        "create": 0,
        "delete": 0,
        "submit": 0,
        "cancel": 0,
        "amend": 0,
        "report": 0,
        "export": 0,
        "import": 0,
        "share": 0,
        "print": 0,
        "email": 0,
    }

    if profile == "full":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "read_report_export":
        base.update({"read": 1, "report": 1, "export": 1, "print": 1})
    elif profile == "read_report":
        base.update({"read": 1, "report": 1})
    else:
        frappe.throw(_("Unknown permission profile: {0}").format(profile))

    return base


def add_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})

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

    if "Sandbox Payment Entry Hygiene" not in text_blob:
        content.append(
            {
                "id": "ndis_sandbox_payment_entry_hygiene_heading",
                "type": "header",
                "data": {"text": "Sandbox Payment Entry Hygiene", "col": 12},
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
    # Workspace child shortcut schemas vary between Frappe versions. The content
    # JSON path above is stable and is enough for Desk rendering and health checks.
    return

    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue

        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue

            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", "Link")
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE3D_DOCTYPES}

    reports = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    permissions = {}
    for dt in PHASE3D_DOCTYPES:
        permissions[dt] = frappe.get_all(
            "DocPerm",
            filters={"parent": dt},
            fields=["role", "read", "write", "create", "delete", "report", "export"],
            order_by="role asc",
        )

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    doc_events = hooks.get("doc_events", {}) or {}
    pe_events_blob = json.dumps(doc_events.get("Payment Entry", {}), default=str)

    return {
        "doctypes": doctypes,
        "reports": reports,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_sandbox_payment_entry_cleanup": permission_matrix().get("run_sandbox_payment_entry_cleanup"),
            "cancel_sandbox_payment_entry_cleanup": permission_matrix().get("cancel_sandbox_payment_entry_cleanup"),
        },
        "js_hooks": {
            "NDIS Sandbox Payment Entry Cleanup Run": "NDIS Sandbox Payment Entry Cleanup Run" in doctype_js,
            "NDIS Sandbox Payment Entry Cleanup Line": "NDIS Sandbox Payment Entry Cleanup Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Sandbox Payment Entry Cleanup Run": "NDIS Sandbox Payment Entry Cleanup Run" in doctype_list_js,
            "NDIS Sandbox Payment Entry Cleanup Line": "NDIS Sandbox Payment Entry Cleanup Line" in doctype_list_js,
        },
        "payment_entry_submit_blocker_still_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.sandbox_payment_entry_cleanup import quick_sandbox_payment_entry_cleanup_summary
        return callable(quick_sandbox_payment_entry_cleanup_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
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
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result


def check_report_files():
    base_path = frappe.get_app_path("ndis_finance", "ndis_finance", "report")
    result = {}

    for report_name, folder in REPORT_FILE_MAP.items():
        folder_path = os.path.join(base_path, folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(folder_path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(folder_path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(folder_path, "__init__.py")),
        }

    return result
