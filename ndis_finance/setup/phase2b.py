import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE2B_DOCTYPES = [
    "NDIS Accounting Posting Policy",
    "NDIS Accounting Posting Preview",
    "NDIS Accounting Posting Preview Line",
]

REPORTS = [
    {"report_name": "NDIS Accounting Posting Policy Register Report", "ref_doctype": "NDIS Accounting Posting Policy"},
    {"report_name": "NDIS Accounting Posting Preview Report", "ref_doctype": "NDIS Accounting Posting Preview"},
]

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Accounting Posting Policy": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Posting Preview": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Posting Preview Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Accounting Posting Policies", "type": "DocType", "link_to": "NDIS Accounting Posting Policy"},
    {"label": "Accounting Posting Previews", "type": "DocType", "link_to": "NDIS Accounting Posting Preview"},
    {"label": "Accounting Preview Lines", "type": "DocType", "link_to": "NDIS Accounting Posting Preview Line"},
    {"label": "Posting Policy Register", "type": "Report", "link_to": "NDIS Accounting Posting Policy Register Report"},
    {"label": "Posting Preview Report", "type": "Report", "link_to": "NDIS Accounting Posting Preview Report"},
]

REPORT_FILE_MAP = {
    "NDIS Accounting Posting Policy Register Report": "ndis_accounting_posting_policy_register_report",
    "NDIS Accounting Posting Preview Report": "ndis_accounting_posting_preview_report",
}

DEFAULT_POLICIES = [
    {
        "policy_id": "NDIS-ACC-POLICY-CLAIM-BATCH",
        "policy_name": "NDIS Claim Batch Accounting Blueprint",
        "event_type": "Claim Batch",
        "source_doctype": "NDIS Claim Batch",
        "target_entry_type": "Sales Invoice",
        "posting_mode": "Management Only",
        "description": "Claim batch revenue is already supported by existing Sales Invoice workflow. This policy documents future accounting integration only.",
        "mapping_notes": "Future logic may reconcile claim batch lines to submitted Sales Invoices; no new Sales Invoice should be created by this preview phase.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-REMITTANCE",
        "policy_name": "NDIS Remittance Payment Allocation Blueprint",
        "event_type": "Remittance",
        "source_doctype": "NDIS Remittance Import",
        "target_entry_type": "Payment Entry",
        "posting_mode": "Preview Only",
        "description": "Defines future preview logic for NDIA remittance receipts and invoice allocation.",
        "mapping_notes": "Future posting must match remittance lines to Sales Invoice and only then create controlled Payment Entry after approval.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-RECOVERY-RECEIPT",
        "policy_name": "NDIS Recovery Receipt Blueprint",
        "event_type": "Recovery Receipt",
        "source_doctype": "NDIS Recovery Case",
        "target_entry_type": "Payment Entry",
        "posting_mode": "Preview Only",
        "description": "Defines future accounting treatment for recovered leakage/shortfall amounts.",
        "mapping_notes": "Future receipt posting must be linked to recovery case and original claim/invoice evidence.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-WRITE-OFF",
        "policy_name": "NDIS Recovery Write-off Blueprint",
        "event_type": "Recovery Write Off",
        "source_doctype": "NDIS Recovery Case",
        "target_entry_type": "Journal Entry",
        "posting_mode": "Preview Only",
        "description": "Defines future controlled accounting treatment for approved recovery write-offs.",
        "mapping_notes": "Future write-off posting must require CFO approval, evidence and management sign-off.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-PAYROLL-COST",
        "policy_name": "AU Payroll Cost Import Accounting Blueprint",
        "event_type": "Payroll Cost Import",
        "source_doctype": "NDIS Payroll Cost Import",
        "target_entry_type": "Journal Entry",
        "posting_mode": "Management Only",
        "description": "Payroll accounting should remain controlled by payroll/HRMS accounting. NDIS payroll import is management profitability costing only.",
        "mapping_notes": "Do not create duplicate payroll accounting from NDIS Finance. Use this only for reconciliation visibility.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-COST-POOL",
        "policy_name": "NDIS Cost Pool Accounting Blueprint",
        "event_type": "Cost Pool Allocation",
        "source_doctype": "NDIS Cost Pool",
        "target_entry_type": "Journal Entry",
        "posting_mode": "Management Only",
        "description": "Cost pools are management costing records. They should not automatically post accounting entries.",
        "mapping_notes": "Future accounting should use source supplier bills, payroll, bank entries, or approved journal policies, not management allocation records directly.",
    },
    {
        "policy_id": "NDIS-ACC-POLICY-GOVERNANCE-ONLY",
        "policy_name": "Governance Pack Management-only Blueprint",
        "event_type": "Governance Pack",
        "source_doctype": "NDIS Executive Governance Pack",
        "target_entry_type": "None",
        "posting_mode": "Management Only",
        "description": "Governance packs are reporting and sign-off records only.",
        "mapping_notes": "No accounting posting should be generated from governance pack records.",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_policy_doctype()
    create_preview_doctype()
    create_preview_line_doctype()
    create_reports()
    seed_default_policies()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Finance Production Readiness Check",
        "NDIS Finance Production Readiness Check Item",
        "NDIS Executive Governance Pack",
        "NDIS Executive Exception Alert",
        "NDIS Executive Exception Action Plan",
        "NDIS Payroll Cost Import",
        "NDIS Cost Pool",
        "NDIS Cost Allocation Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 2B requires Phase 2A and the Phase 1 control layer. Missing DocTypes: {0}").format(", ".join(missing)))


def create_policy_doctype():
    _create_doctype(
        name="NDIS Accounting Posting Policy",
        autoname="field:policy_id",
        title_field="policy_name",
        fields=[
            {"fieldname": "policy_id", "label": "Policy ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "policy_name", "label": "Policy Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "policy_status", "label": "Policy Status", "fieldtype": "Select", "options": "\nDraft\nActive\nSuspended\nRetired", "default": "Active", "in_list_view": 1},
            {"fieldname": "active", "label": "Active", "fieldtype": "Check", "default": "1", "in_list_view": 1},
            {"fieldname": "policy_section", "label": "Policy Scope", "fieldtype": "Section Break"},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Select", "options": "\nClaim Batch\nRemittance\nRecovery Receipt\nRecovery Write Off\nPayroll Cost Import\nCost Pool Allocation\nGovernance Pack\nOther", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType", "reqd": 1, "in_list_view": 1},
            {"fieldname": "target_entry_type", "label": "Target Entry Type", "fieldtype": "Select", "options": "\nNone\nSales Invoice\nPayment Entry\nJournal Entry\nPurchase Invoice\nGL Entry", "default": "None", "in_list_view": 1},
            {"fieldname": "posting_mode", "label": "Posting Mode", "fieldtype": "Select", "options": "\nManagement Only\nPreview Only\nFuture Controlled Posting\nDisabled", "default": "Preview Only", "in_list_view": 1},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "requires_readiness_check", "label": "Requires Production Readiness Check", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_governance_pack_signoff", "label": "Requires Governance Pack Sign-off", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_cfo_approval", "label": "Requires CFO Approval", "fieldtype": "Check", "default": "1"},
            {"fieldname": "allow_auto_submit", "label": "Allow Auto Submit", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_sales_invoice", "label": "Allow Sales Invoice Creation", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_payment_entry", "label": "Allow Payment Entry Creation", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_journal_entry", "label": "Allow Journal Entry Creation", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_gl_entry", "label": "Allow GL Entry Creation", "fieldtype": "Check", "default": "0"},
            {"fieldname": "mapping_section", "label": "Accounting Mapping Placeholder", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "default_debit_account", "label": "Default Debit Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "default_credit_account", "label": "Default Credit Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "default_cost_center", "label": "Default Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "tax_treatment", "label": "Tax Treatment", "fieldtype": "Data"},
            {"fieldname": "description", "label": "Description", "fieldtype": "Small Text"},
            {"fieldname": "mapping_notes", "label": "Mapping Notes", "fieldtype": "Long Text"},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "last_preview_on", "label": "Last Preview On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "last_preview", "label": "Last Preview", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "preview_count", "label": "Preview Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_preview_doctype():
    _create_doctype(
        name="NDIS Accounting Posting Preview",
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "validation_status", "label": "Validation Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocked", "default": "Warning", "in_list_view": 1},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "policy", "label": "Posting Policy", "fieldtype": "Link", "options": "NDIS Accounting Posting Policy", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_status", "label": "Source Status", "fieldtype": "Data"},
            {"fieldname": "source_summary", "label": "Source Summary", "fieldtype": "Small Text"},
            {"fieldname": "control_section", "label": "Control Gate", "fieldtype": "Section Break"},
            {"fieldname": "readiness_check", "label": "Production Readiness Check", "fieldtype": "Link", "options": "NDIS Finance Production Readiness Check"},
            {"fieldname": "readiness_allowed", "label": "Readiness Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "governance_pack", "label": "Governance Pack", "fieldtype": "Link", "options": "NDIS Executive Governance Pack"},
            {"fieldname": "governance_signed_off", "label": "Governance Signed Off", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "cfo_approval_required", "label": "CFO Approval Required", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "posting_section", "label": "Posting Blueprint", "fieldtype": "Section Break"},
            {"fieldname": "target_entry_type", "label": "Target Entry Type", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "posting_mode", "label": "Posting Mode", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "preview_total_amount", "label": "Preview Total Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "preview_only_confirmation", "label": "Preview-only Confirmation", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_preview_line_doctype():
    _create_doctype(
        name="NDIS Accounting Posting Preview Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "posting_preview", "label": "Posting Preview", "fieldtype": "Link", "options": "NDIS Accounting Posting Preview", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPreview\nWarning\nBlocker\nCancelled", "default": "Preview", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "line_type", "label": "Line Type", "fieldtype": "Select", "options": "\nDebit\nCredit\nControl\nInformation", "default": "Information", "in_list_view": 1},
            {"fieldname": "target_entry_type", "label": "Target Entry Type", "fieldtype": "Data"},
            {"fieldname": "account", "label": "Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "party_type", "label": "Party Type", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "party", "label": "Party", "fieldtype": "Dynamic Link", "options": "party_type"},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "reference_doctype", "label": "Reference DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "reference_name", "label": "Reference Name", "fieldtype": "Dynamic Link", "options": "reference_doctype"},
            {"fieldname": "note", "label": "Note", "fieldtype": "Small Text"},
        ],
    )


def create_reports():
    for report in REPORTS:
        doc = frappe.get_doc("Report", report["report_name"]) if frappe.db.exists("Report", report["report_name"]) else frappe.new_doc("Report")
        doc.report_name = report["report_name"]
        doc.ref_doctype = report["ref_doctype"]
        doc.report_type = "Script Report"
        doc.module = MODULE
        doc.is_standard = "Yes"
        doc.disabled = 0
        doc.roles = []
        for role in REPORT_ROLES:
            if frappe.db.exists("Role", role):
                doc.append("roles", {"role": role})
        doc.save(ignore_permissions=True)


def seed_default_policies():
    for policy in DEFAULT_POLICIES:
        doc = frappe.get_doc("NDIS Accounting Posting Policy", policy["policy_id"]) if frappe.db.exists("NDIS Accounting Posting Policy", policy["policy_id"]) else frappe.new_doc("NDIS Accounting Posting Policy")
        doc.policy_id = policy["policy_id"]
        doc.policy_status = "Active"
        doc.active = 1
        doc.requires_readiness_check = 1
        doc.requires_governance_pack_signoff = 1
        doc.requires_cfo_approval = 1
        doc.allow_auto_submit = 0
        doc.allow_sales_invoice = 0
        doc.allow_payment_entry = 0
        doc.allow_journal_entry = 0
        doc.allow_gl_entry = 0
        for key, value in policy.items():
            setattr(doc, key, value)
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
    base = {"role": role, "permlevel": 0, "read": 0, "write": 0, "create": 0, "delete": 0, "submit": 0, "cancel": 0, "amend": 0, "report": 0, "export": 0, "import": 0, "share": 0, "print": 0, "email": 0}
    if profile == "full":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "full_no_delete":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
    elif profile == "create_write_read_report":
        base.update({"read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "print": 1, "email": 1})
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
    if "Accounting Blueprint" not in text_blob:
        content.append({"id": "ndis_accounting_blueprint_heading", "type": "header", "data": {"text": "Accounting Blueprint", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


def add_shortcuts_to_child_table(ws):
    for fieldname in ["shortcuts", "links"]:
        if not ws.meta.has_field(fieldname):
            continue
        existing_blob = " ".join(f"{getattr(row, 'label', '')} {getattr(row, 'link_to', '')}" for row in (getattr(ws, fieldname, []) or []))
        for shortcut in WORKSPACE_SHORTCUTS:
            if shortcut["label"] in existing_blob or shortcut["link_to"] in existing_blob:
                continue
            row = ws.append(fieldname, {})
            set_child_value(row, "label", shortcut["label"])
            set_child_value(row, "link_to", shortcut["link_to"])
            set_child_value(row, "type", shortcut["type"] if fieldname == "shortcuts" else "Link")
            set_child_value(row, "link_type", shortcut["type"])
            set_child_value(row, "open_in_new_tab", 0)
            if shortcut["type"] == "Report":
                set_child_value(row, "is_query_report", 1)
                set_child_value(row, "report_ref_doctype", report_ref_doctype(shortcut["link_to"]))


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
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    return {
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE2B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "default_policies": {policy["policy_id"]: bool(frappe.db.exists("NDIS Accounting Posting Policy", policy["policy_id"])) for policy in DEFAULT_POLICIES},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE2B_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_accounting_posting_policy": permission_matrix().get("manage_accounting_posting_policy"),
            "create_accounting_posting_preview": permission_matrix().get("create_accounting_posting_preview"),
            "cancel_accounting_posting_preview": permission_matrix().get("cancel_accounting_posting_preview"),
        },
        "js_hooks": {
            "NDIS Accounting Posting Policy": "NDIS Accounting Posting Policy" in doctype_js,
            "NDIS Accounting Posting Preview": "NDIS Accounting Posting Preview" in doctype_js,
            "NDIS Accounting Posting Preview Line": "NDIS Accounting Posting Preview Line" in doctype_js,
        },
        "list_js_hooks": {
            "NDIS Accounting Posting Policy": "NDIS Accounting Posting Policy" in doctype_list_js,
            "NDIS Accounting Posting Preview": "NDIS Accounting Posting Preview" in doctype_list_js,
            "NDIS Accounting Posting Preview Line": "NDIS Accounting Posting Preview Line" in doctype_list_js,
        },
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.accounting_posting_blueprint import quick_accounting_policy_summary

        return callable(quick_accounting_policy_summary)
    except Exception:
        return False


def check_report_files():
    app_path = frappe.get_app_path("ndis_finance")
    result = {}
    for report_name, folder in REPORT_FILE_MAP.items():
        path = os.path.join(app_path, "ndis_finance", "report", folder)
        result[report_name] = {
            "python": os.path.exists(os.path.join(path, f"{folder}.py")),
            "javascript": os.path.exists(os.path.join(path, f"{folder}.js")),
            "init": os.path.exists(os.path.join(path, "__init__.py")),
        }
    return result


def check_workspace_shortcuts():
    ws_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists("Workspace", {"label": WORKSPACE_NAME})
    result = {shortcut["label"]: False for shortcut in WORKSPACE_SHORTCUTS}
    if not ws_name:
        return result
    ws = frappe.get_doc("Workspace", ws_name)
    text_blob = getattr(ws, "content", None) or ""
    for fieldname in ["shortcuts", "links"]:
        if ws.meta.has_field(fieldname):
            for row in getattr(ws, fieldname, []) or []:
                text_blob += f" {getattr(row, 'label', '')} {getattr(row, 'link_to', '')}"
    for shortcut in WORKSPACE_SHORTCUTS:
        result[shortcut["label"]] = shortcut["label"] in text_blob or shortcut["link_to"] in text_blob
    return result
