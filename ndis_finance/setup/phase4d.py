import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


FREEZE_DOCTYPE = "NDIS PE Sandbox Readiness Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS PE Sandbox Readiness Freeze Item"

PHASE4D_DOCTYPES = [FREEZE_DOCTYPE, FREEZE_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS PE Sandbox Readiness Freeze Report", "ref_doctype": FREEZE_DOCTYPE},
    {"report_name": "NDIS PE Sandbox Readiness Freeze Item Report", "ref_doctype": FREEZE_ITEM_DOCTYPE},
]

REPORT_FILE_MAP = {
    "NDIS PE Sandbox Readiness Freeze Report": "ndis_pe_sandbox_readiness_freeze_report",
    "NDIS PE Sandbox Readiness Freeze Item Report": "ndis_pe_sandbox_readiness_freeze_item_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    FREEZE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    FREEZE_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "PE Sandbox Readiness Freezes", "type": "DocType", "link_to": FREEZE_DOCTYPE},
    {"label": "PE Sandbox Readiness Freeze Items", "type": "DocType", "link_to": FREEZE_ITEM_DOCTYPE},
    {"label": "PE Sandbox Readiness Freeze Report", "type": "Report", "link_to": "NDIS PE Sandbox Readiness Freeze Report"},
    {"label": "PE Sandbox Freeze Item Report", "type": "Report", "link_to": "NDIS PE Sandbox Readiness Freeze Item Report"},
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_freeze_doctype()
    create_freeze_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Sandbox Accounting Cleanup Pack",
        get_cleanup_line_doctype(),
        "NDIS Invoice Backed PE Smoke Run",
        "NDIS Sandbox Invoice Test Run",
        "NDIS Payment Entry Sandbox Completion Gate",
        "NDIS Sandbox Payment Entry Run",
        "NDIS Payment Entry Allocation Preview",
        "NDIS Accounting Design Review",
        "Payment Entry",
        "Sales Invoice",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(_("Phase 4D requires Phase 4C and the full Payment Entry sandbox chain. Missing: {0}").format(", ".join(missing)))


def get_cleanup_line_doctype():
    if frappe.db.exists("DocType", "NDIS Sandbox Accounting Cleanup Pack Line"):
        return "NDIS Sandbox Accounting Cleanup Pack Line"
    return "NDIS Sandbox Accounting Cleanup Line"


def create_freeze_doctype():
    _create_doctype(
        name=FREEZE_DOCTYPE,
        autoname="field:freeze_id",
        title_field="freeze_id",
        fields=[
            {"fieldname": "freeze_id", "label": "Freeze ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nFrozen\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "freeze_type", "label": "Freeze Type", "fieldtype": "Select", "options": "\nPayment Entry Sandbox Readiness\nPre-Live Payment Entry Readiness", "default": "Payment Entry Sandbox Readiness", "in_list_view": 1},
            {"fieldname": "readiness_allowed", "label": "Readiness Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "ready_for_next_design_phase", "label": "Ready For Next Design Phase", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "frozen_on", "label": "Frozen On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "frozen_by", "label": "Frozen By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Readiness Score", "fieldtype": "Section Break"},
            {"fieldname": "readiness_score", "label": "Readiness Score", "fieldtype": "Percent", "read_only": 1, "in_list_view": 1},
            {"fieldname": "readiness_status", "label": "Readiness Status", "fieldtype": "Select", "options": "\nReady For Next Design Phase\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "evidence_section", "label": "Evidence Counts", "fieldtype": "Section Break"},
            {"fieldname": "design_review_count", "label": "Approved Design Review Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "allocation_preview_count", "label": "Allocation Preview Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "draft_pe_run_count", "label": "Draft PE Run Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_backed_smoke_count", "label": "Invoice-backed Smoke Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cleanup_pack_count", "label": "Cleanup Pack Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase3e_cleared_gate_count", "label": "Phase 3E Cleared Gate Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "hygiene_section", "label": "Sandbox Hygiene", "fieldtype": "Section Break"},
            {"fieldname": "draft_sandbox_pe_count", "label": "Draft Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_sandbox_pe_count", "label": "Submitted Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_sandbox_si_count", "label": "Submitted Sandbox SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cancelled_sandbox_si_count", "label": "Cancelled Sandbox SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "draft_sandbox_si_count", "label": "Draft Sandbox SI Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sandbox_si_gl_count", "label": "Sandbox SI GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sandbox_si_gl_net", "label": "Sandbox SI GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Strict Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "submitted_payment_entry_count_today", "label": "Submitted PE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_today", "label": "Payment Entry GL Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "unrelated_gl_count_today", "label": "Unrelated GL Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_freeze_item_doctype():
    _create_doctype(
        name=FREEZE_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "readiness_freeze", "label": "Readiness Freeze", "fieldtype": "Link", "options": FREEZE_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def create_reports():
    for report in REPORTS:
        ensure_script_report(report["report_name"], report["ref_doctype"])


def ensure_script_report(report_name, ref_doctype):
    existing = frappe.db.exists("Report", report_name)
    doc = frappe.get_doc("Report", existing) if existing else frappe.new_doc("Report")
    if not existing:
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
    ws.save(ignore_permissions=True)


def add_shortcuts_to_content_json(ws):
    if not ws.meta.has_field("content"):
        return

    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []

    text_blob = json.dumps(content)

    if "Payment Entry Sandbox Readiness Freeze" not in text_blob:
        content.append(
            {
                "id": "ndis_pe_sandbox_readiness_freeze_heading",
                "type": "header",
                "data": {"text": "Payment Entry Sandbox Readiness Freeze", "col": 12},
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


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE4D_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}

    permissions = {}
    for dt in PHASE4D_DOCTYPES:
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
    si_events_blob = json.dumps(doc_events.get("Sales Invoice", {}), default=str)

    return {
        "doctypes": doctypes,
        "reports": reports,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_sandbox_readiness_freeze": permission_matrix().get("run_pe_sandbox_readiness_freeze"),
            "cancel_pe_sandbox_readiness_freeze": permission_matrix().get("cancel_pe_sandbox_readiness_freeze"),
        },
        "js_hooks": {
            FREEZE_DOCTYPE: FREEZE_DOCTYPE in doctype_js,
            FREEZE_ITEM_DOCTYPE: FREEZE_ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            FREEZE_DOCTYPE: FREEZE_DOCTYPE in doctype_list_js,
            FREEZE_ITEM_DOCTYPE: FREEZE_ITEM_DOCTYPE in doctype_list_js,
        },
        "payment_entry_submit_blocker_still_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sales_invoice_submit_safety_still_registered": "block_unacknowledged_sandbox_sales_invoice_submit" in si_events_blob,
        "phase4c_cleanup_line_doctype_detected": get_cleanup_line_doctype(),
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.pe_sandbox_readiness_freeze import quick_pe_sandbox_readiness_freeze_summary

        return callable(quick_pe_sandbox_readiness_freeze_summary)
    except Exception:
        return False


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result

    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result


def check_report_files():
    app_path = frappe.get_app_path("ndis_finance")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        report_dir = os.path.join(app_path, "ndis_finance", "report", folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(report_dir, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(report_dir, f"{folder}.js")),
            "init": os.path.exists(os.path.join(report_dir, "__init__.py")),
        }
    return result
