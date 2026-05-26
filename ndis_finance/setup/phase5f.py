import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.services.permissions import permission_matrix
from ndis_finance.setup.install import MODULE, _create_doctype


RUN_DOCTYPE = "NDIS PE Single Record Draft Smoke Run"
ITEM_DOCTYPE = "NDIS PE Single Record Draft Smoke Run Item"

PHASE5F_DOCTYPES = [
    RUN_DOCTYPE,
    ITEM_DOCTYPE,
]

REPORTS = [
    {
        "report_name": "NDIS PE Single Record Draft Smoke Run Report",
        "ref_doctype": RUN_DOCTYPE,
        "module_path": "ndis_pe_single_record_draft_smoke_run_report",
    },
    {
        "report_name": "NDIS PE Single Record Draft Smoke Exception Report",
        "ref_doctype": ITEM_DOCTYPE,
        "module_path": "ndis_pe_single_record_draft_smoke_exception_report",
    },
    {
        "report_name": "NDIS PE Draft Smoke Payment Entry Hygiene Report",
        "ref_doctype": "Payment Entry",
        "module_path": "ndis_pe_draft_smoke_payment_entry_hygiene_report",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
]

DOC_PERM_MATRIX = {
    RUN_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

PAYMENT_ENTRY_FIELDS = [
    "custom_ndis_pe_draft_smoke_section",
    "custom_ndis_pe_single_record_draft_smoke",
    "custom_ndis_pe_draft_smoke_run",
    "custom_ndis_pe_activation_gate",
    "custom_ndis_pe_source_preview_line",
    "custom_ndis_pe_draft_smoke_note",
]

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {
        "label": "PE Single-record Draft Smoke Runs",
        "type": "DocType",
        "link_to": RUN_DOCTYPE,
    },
    {
        "label": "PE Draft Smoke Run Items",
        "type": "DocType",
        "link_to": ITEM_DOCTYPE,
    },
    {
        "label": "PE Draft Smoke Run Report",
        "type": "Report",
        "link_to": "NDIS PE Single Record Draft Smoke Run Report",
    },
    {
        "label": "PE Draft Smoke Exceptions",
        "type": "Report",
        "link_to": "NDIS PE Single Record Draft Smoke Exception Report",
    },
    {
        "label": "PE Draft Smoke Hygiene",
        "type": "Report",
        "link_to": "NDIS PE Draft Smoke Payment Entry Hygiene Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_payment_entry_custom_fields()
    create_smoke_run_doctype()
    create_smoke_run_item_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Production Activation Gate",
        "NDIS PE Production Activation Gate Item",
        "NDIS PE Production Adapter Run",
        "NDIS PE Production Posting Preview",
        "NDIS PE Production Posting Preview Line",
        "NDIS PE Production Posting Policy",
        "Payment Entry",
        "Sales Invoice",
        "GL Entry",
        "Account",
        "Company",
        "Report",
        "Workspace",
    ]

    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 5F requires completed Phase 5E activation gate. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_payment_entry_custom_fields():
    fields = {
        "Payment Entry": [
            {
                "fieldname": "custom_ndis_pe_draft_smoke_section",
                "label": "NDIS PE Draft Smoke",
                "fieldtype": "Section Break",
                "insert_after": "remarks",
            },
            {
                "fieldname": "custom_ndis_pe_single_record_draft_smoke",
                "label": "NDIS Single-record Draft Smoke",
                "fieldtype": "Check",
                "insert_after": "custom_ndis_pe_draft_smoke_section",
                "default": "0",
                "read_only": 1,
            },
            {
                "fieldname": "custom_ndis_pe_draft_smoke_run",
                "label": "NDIS PE Draft Smoke Run",
                "fieldtype": "Link",
                "options": RUN_DOCTYPE,
                "insert_after": "custom_ndis_pe_single_record_draft_smoke",
                "read_only": 1,
            },
            {
                "fieldname": "custom_ndis_pe_activation_gate",
                "label": "NDIS PE Activation Gate",
                "fieldtype": "Link",
                "options": "NDIS PE Production Activation Gate",
                "insert_after": "custom_ndis_pe_draft_smoke_run",
                "read_only": 1,
            },
            {
                "fieldname": "custom_ndis_pe_source_preview_line",
                "label": "NDIS PE Source Preview Line",
                "fieldtype": "Link",
                "options": "NDIS PE Production Posting Preview Line",
                "insert_after": "custom_ndis_pe_activation_gate",
                "read_only": 1,
            },
            {
                "fieldname": "custom_ndis_pe_draft_smoke_note",
                "label": "NDIS PE Draft Smoke Note",
                "fieldtype": "Small Text",
                "insert_after": "custom_ndis_pe_source_preview_line",
                "read_only": 1,
            },
        ]
    }

    create_custom_fields(fields, ignore_validate=True)


def create_smoke_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:smoke_run_id",
        title_field="smoke_run_id",
        fields=[
            {"fieldname": "smoke_run_id", "label": "Smoke Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nSource Pending\nDraft Created\nSubmit Block Verified\nCleaned\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "smoke_mode", "label": "Smoke Mode", "fieldtype": "Select", "options": "\nReadiness Only\nExplicit Sales Invoice\nPreview Line With Invoice", "default": "Readiness Only", "in_list_view": 1},
            {"fieldname": "activation_gate", "label": "Phase 5E Activation Gate", "fieldtype": "Link", "options": "NDIS PE Production Activation Gate", "in_list_view": 1},
            {"fieldname": "source_preview_line", "label": "Source Preview Line", "fieldtype": "Link", "options": "NDIS PE Production Posting Preview Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice"},
            {"fieldname": "draft_payment_entry", "label": "Draft Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "in_list_view": 1},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "draft_amount", "label": "Draft Amount", "fieldtype": "Currency"},
            {"fieldname": "invoice_outstanding_amount", "label": "Invoice Outstanding Amount", "fieldtype": "Currency"},
            {"fieldname": "invoice_backed_source_required", "label": "Invoice-backed Source Required", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "draft_payment_entry_created", "label": "Draft Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "draft_payment_entry_submitted", "label": "Draft Payment Entry Submitted", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "submit_block_verified", "label": "Submit Block Verified", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cleanup_required", "label": "Cleanup Required", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "executed_on", "label": "Executed On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "executed_by", "label": "Executed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Smoke Score", "fieldtype": "Section Break"},
            {"fieldname": "smoke_score", "label": "Smoke Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "smoke_status", "label": "Smoke Status", "fieldtype": "Select", "options": "\nReady For Draft PE\nDraft PE Created\nSource Pending\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Strict Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_payment_entry_count_today", "label": "Submitted PE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_today", "label": "Payment Entry GL Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cleaned_on", "label": "Cleaned On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cleaned_by", "label": "Cleaned By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_smoke_run_item_doctype():
    _create_doctype(
        name=ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "smoke_run", "label": "Smoke Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
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
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace", {"label": WORKSPACE_NAME}
    )

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

    if "Single-record Draft Payment Entry Smoke" not in text_blob:
        content.append(
            {
                "id": "ndis_pe_single_record_draft_smoke_heading",
                "type": "header",
                "data": {"text": "Single-record Draft Payment Entry Smoke", "col": 12},
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

        existing_blob = ""
        for row in getattr(ws, fieldname, []) or []:
            existing_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue

            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", shortcut["type"])
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)


def set_child_value(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5F_DOCTYPES}

    reports = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    payment_entry_fields = {
        fieldname: bool(frappe.db.exists("Custom Field", f"Payment Entry-{fieldname}"))
        for fieldname in PAYMENT_ENTRY_FIELDS
    }

    permissions = {}
    for dt in PHASE5F_DOCTYPES:
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
        "report_files": check_report_files(),
        "payment_entry_fields": payment_entry_fields,
        "permissions": permissions,
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_pe_single_record_draft_smoke": permission_matrix().get("run_pe_single_record_draft_smoke"),
            "cleanup_pe_single_record_draft_smoke": permission_matrix().get("cleanup_pe_single_record_draft_smoke"),
            "cancel_pe_single_record_draft_smoke": permission_matrix().get("cancel_pe_single_record_draft_smoke"),
            "verify_pe_single_record_draft_submit_block": permission_matrix().get("verify_pe_single_record_draft_submit_block"),
        },
        "js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_list_js,
            ITEM_DOCTYPE: ITEM_DOCTYPE in doctype_list_js,
        },
        "payment_entry_submit_blocker_registered": "block_single_record_draft_smoke_submit" in pe_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def can_import_service():
    try:
        from ndis_finance.services.pe_single_record_draft_smoke import quick_pe_single_record_draft_smoke_summary

        return callable(quick_pe_single_record_draft_smoke_summary)
    except Exception:
        return False


def check_report_files():
    base_path = frappe.get_app_path("ndis_finance", "ndis_finance", "report")
    result = {}

    for report in REPORTS:
        module_path = report["module_path"]
        result[report["report_name"]] = {
            "python": os.path.exists(os.path.join(base_path, module_path, f"{module_path}.py")),
            "javascript": os.path.exists(os.path.join(base_path, module_path, f"{module_path}.js")),
        }

    return result


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace", {"label": WORKSPACE_NAME}
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
                text_blob += " " + str(getattr(row, "label", "")) + " " + str(getattr(row, "link_to", ""))

    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True

    return result
