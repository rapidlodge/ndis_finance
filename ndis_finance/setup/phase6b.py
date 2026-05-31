import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PREVIEW_DOCTYPE = "NDIS Real Remittance PE Preview"
LINE_DOCTYPE = "NDIS Real Remittance PE Preview Line"
PHASE6B_DOCTYPES = [PREVIEW_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance PE Preview Report",
        "ref_doctype": PREVIEW_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_preview_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Preview Line Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_preview_line_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Preview Exception Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_preview_exception_report",
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
    PREVIEW_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    LINE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "Real Remittance PE Previews", "type": "DocType", "link_to": PREVIEW_DOCTYPE},
    {"label": "Real Remittance PE Preview Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {
        "label": "Real Remittance PE Preview Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Preview Report",
    },
    {
        "label": "Real Remittance PE Preview Lines Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Preview Line Report",
    },
    {
        "label": "Real Remittance PE Preview Exceptions",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Preview Exception Report",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_preview_doctype()
    create_preview_line_doctype()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance PE Design Gate",
        "NDIS Real Remittance PE Design Gate Item",
        "NDIS Remittance Import",
        "NDIS Remittance Import Line",
        "NDIS Claim Line",
        "Sales Invoice",
        "Payment Entry",
        "Payment Entry Reference",
        "GL Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 6B requires completed Phase 6A design gate and remittance foundation. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_preview_doctype():
    _create_doctype(
        name=PREVIEW_DOCTYPE,
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "preview_type", "label": "Preview Type", "fieldtype": "Select", "options": "\nLimited Real Remittance To Payment Entry\nPreview Only", "default": "Limited Real Remittance To Payment Entry", "in_list_view": 1},
            {"fieldname": "design_gate", "label": "Phase 6A Design Gate", "fieldtype": "Link", "options": "NDIS Real Remittance PE Design Gate", "in_list_view": 1},
            {"fieldname": "preview_approved_for_adapter_phase", "label": "Preview Approved For Adapter Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "scope_section", "label": "Scope", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "source_remittance_import", "label": "Source Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import", "in_list_view": 1},
            {"fieldname": "batch_line_cap", "label": "Batch Line Cap", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "batch_amount_cap", "label": "Batch Amount Cap", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "count_section", "label": "Line Counts", "fieldtype": "Section Break"},
            {"fieldname": "source_line_count", "label": "Source Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_line_count", "label": "Eligible Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocked_line_count", "label": "Blocked Line Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "review_line_count", "label": "Review Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_paid_line_count", "label": "Eligible Paid Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "eligible_short_paid_line_count", "label": "Eligible Short Paid Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_rejected_line_count", "label": "Blocked Rejected Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_duplicate_line_count", "label": "Blocked Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_unmatched_line_count", "label": "Blocked Unmatched Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_overpayment_line_count", "label": "Blocked Overpayment Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_cross_company_line_count", "label": "Blocked Cross-company Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_missing_invoice_line_count", "label": "Blocked Missing Invoice Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_batch_cap_line_count", "label": "Blocked Batch Cap Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "amount_section", "label": "Amounts", "fieldtype": "Section Break"},
            {"fieldname": "eligible_amount", "label": "Eligible Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocked_amount", "label": "Blocked Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "review_amount", "label": "Review Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "would_create_payment_entry_count", "label": "Would Create Payment Entry Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "actual_payment_entry_created_count", "label": "Actual Payment Entry Created Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Preview Score", "fieldtype": "Section Break"},
            {"fieldname": "preview_score", "label": "Preview Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nReady For Hard-block Adapter\nPreviewed With Exceptions\nNeeds Review\nBlocked", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_count_today", "label": "Sales Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
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


def create_preview_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="classification",
        fields=[
            {"fieldname": "preview", "label": "Preview", "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_remittance_import", "label": "Source Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import", "in_list_view": 1},
            {"fieldname": "source_remittance_line", "label": "Source Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line", "in_list_view": 1},
            {"fieldname": "source_outcome", "label": "Source Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "classification", "label": "Classification", "fieldtype": "Select", "options": "\nEligible Paid\nEligible Short Paid\nBlocked Rejected\nBlocked Duplicate\nBlocked Unmatched\nBlocked Overpayment\nBlocked Cross-company\nBlocked Missing Invoice / Claim Line\nBlocked Batch Cap\nReview Required", "in_list_view": 1},
            {"fieldname": "preview_status", "label": "Preview Status", "fieldtype": "Select", "options": "\nEligible\nBlocked\nReview\nCancelled", "in_list_view": 1},
            {"fieldname": "block_reason", "label": "Block / Review Reason", "fieldtype": "Small Text"},
            {"fieldname": "mapping_section", "label": "Mapping", "fieldtype": "Section Break"},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "amount_section", "label": "Amounts", "fieldtype": "Section Break"},
            {"fieldname": "source_amount", "label": "Source Amount", "fieldtype": "Currency"},
            {"fieldname": "allocatable_amount", "label": "Allocatable Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "invoice_outstanding_amount", "label": "Invoice Outstanding Amount", "fieldtype": "Currency"},
            {"fieldname": "shortfall_amount", "label": "Shortfall Amount", "fieldtype": "Currency"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "would_create_payment_entry", "label": "Would Create Payment Entry", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "payment_entry_created", "label": "Payment Entry Created", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "duplicate_detected", "label": "Duplicate Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "overpayment_detected", "label": "Overpayment Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cross_company_detected", "label": "Cross-company Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "batch_cap_blocked", "label": "Batch Cap Blocked", "fieldtype": "Check", "read_only": 1},
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
    if not ws.meta.has_field("content"):
        return
    try:
        content = json.loads(ws.content or "[]")
    except Exception:
        content = []
    text_blob = json.dumps(content)
    if "Real Remittance Payment Entry Preview" not in text_blob:
        content.append(
            {
                "id": "ndis_real_remittance_pe_preview_heading",
                "type": "header",
                "data": {"text": "Real Remittance Payment Entry Preview", "col": 12},
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
    ws.save(ignore_permissions=True)


@frappe.whitelist()
def health_check():
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE6B_DOCTYPES},
        "reports": {
            report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
            for report in REPORTS
        },
        "report_files": check_report_files(),
        "permissions": {
            dt: frappe.get_all(
                "DocPerm",
                filters={"parent": dt},
                fields=["role", "read", "write", "create", "delete", "report", "export"],
                order_by="role asc",
            )
            for dt in PHASE6B_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_pe_preview": permission_matrix().get("run_real_remittance_pe_preview"),
            "cancel_real_remittance_pe_preview": permission_matrix().get("cancel_real_remittance_pe_preview"),
        },
        "js_hooks": {
            PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            PREVIEW_DOCTYPE: PREVIEW_DOCTYPE in doctype_list_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(
            frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0
        ),
    }


def can_import_service():
    try:
        from ndis_finance.services.real_remittance_pe_preview import quick_real_remittance_pe_preview_summary

        return callable(quick_real_remittance_pe_preview_summary)
    except Exception:
        return False


def check_report_files():
    report_root = Path(frappe.get_app_path("ndis_finance")) / "ndis_finance" / "report"
    return {
        report["report_name"]: {
            "python": (report_root / report["module_path"] / f"{report['module_path']}.py").exists(),
            "javascript": (report_root / report["module_path"] / f"{report['module_path']}.js").exists(),
        }
        for report in REPORTS
    }


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = ws.content or ""
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
