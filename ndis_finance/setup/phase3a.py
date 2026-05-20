import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE3A_DOCTYPES = [
    "NDIS Accounting Design Matrix",
    "NDIS Accounting Design Review",
    "NDIS Accounting Design Review Item",
]

REPORTS = [
    {"report_name": "NDIS Accounting Design Matrix Report", "ref_doctype": "NDIS Accounting Design Matrix"},
    {"report_name": "NDIS Accounting Design Review Report", "ref_doctype": "NDIS Accounting Design Review"},
    {"report_name": "NDIS Accounting Design Exception Report", "ref_doctype": "NDIS Accounting Design Review Item"},
]

REPORT_FILE_MAP = {
    "NDIS Accounting Design Matrix Report": "ndis_accounting_design_matrix_report",
    "NDIS Accounting Design Review Report": "ndis_accounting_design_review_report",
    "NDIS Accounting Design Exception Report": "ndis_accounting_design_exception_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Accounting Design Matrix": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Design Review": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Accounting Design Review Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Accounting Design Matrix", "type": "DocType", "link_to": "NDIS Accounting Design Matrix"},
    {"label": "Accounting Design Reviews", "type": "DocType", "link_to": "NDIS Accounting Design Review"},
    {"label": "Accounting Design Review Items", "type": "DocType", "link_to": "NDIS Accounting Design Review Item"},
    {"label": "Accounting Design Matrix Report", "type": "Report", "link_to": "NDIS Accounting Design Matrix Report"},
    {"label": "Accounting Design Review Report", "type": "Report", "link_to": "NDIS Accounting Design Review Report"},
    {"label": "Accounting Design Exceptions", "type": "Report", "link_to": "NDIS Accounting Design Exception Report"},
]

DEFAULT_MATRIX = [
    {
        "matrix_id": "NDIS-ACC-DESIGN-CLAIM-BATCH",
        "design_name": "Claim Batch Revenue Reconciliation Design",
        "event_type": "Claim Batch",
        "source_doctype": "NDIS Claim Batch",
        "accounting_treatment": "Reconcile Existing Sales Invoice",
        "allowed_target_doctype": "Sales Invoice",
        "posting_route": "Existing ERPNext Invoice Flow",
        "design_status": "Active",
        "risk_level": "High",
        "xero_export_allowed_later": 1,
        "duplicate_prevention_rule": "Do not create a second Sales Invoice from a claim batch. Reconcile against existing submitted invoices.",
        "failure_handling_rule": "If invoice matching fails, block posting and route to exception review.",
        "rollback_rule": "Future rollback must use native ERPNext cancellation or reversal workflow.",
        "design_notes": "Claim batches are not a second source of revenue recognition.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-REMITTANCE",
        "design_name": "NDIS Remittance Payment Allocation Design",
        "event_type": "Remittance",
        "source_doctype": "NDIS Remittance Import",
        "accounting_treatment": "Future Controlled Payment Allocation",
        "allowed_target_doctype": "Payment Entry",
        "posting_route": "Future Controlled ERPNext Payment Entry",
        "design_status": "Active",
        "risk_level": "Critical",
        "payment_entry_allowed_later": 1,
        "xero_export_allowed_later": 1,
        "duplicate_prevention_rule": "NDIA receipt reference, remittance import line and invoice allocation must be unique.",
        "failure_handling_rule": "Short-paid or rejected lines must go to leakage/recovery, not forced allocation.",
        "rollback_rule": "Future rollback must cancel Payment Entry and reopen allocation status.",
        "design_notes": "Likely future Payment Entry sandbox adapter, not implemented in Phase 3A.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-RECOVERY-RECEIPT",
        "design_name": "Recovery Receipt Accounting Design",
        "event_type": "Recovery Receipt",
        "source_doctype": "NDIS Recovery Case",
        "accounting_treatment": "Future Controlled Payment Receipt",
        "allowed_target_doctype": "Payment Entry",
        "posting_route": "Future Controlled ERPNext Payment Entry",
        "design_status": "Active",
        "risk_level": "High",
        "payment_entry_allowed_later": 1,
        "xero_export_allowed_later": 1,
        "duplicate_prevention_rule": "Recovery receipt must not duplicate remittance receipt or invoice allocation.",
        "failure_handling_rule": "If the recovery case is not approved or resolved, block receipt posting.",
        "rollback_rule": "Future rollback must cancel Payment Entry and reopen recovery accounting status.",
        "design_notes": "Recovery receipt must stay evidence-linked to the original leakage/claim/invoice.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-WRITE-OFF",
        "design_name": "Recovery Write-off Accounting Design",
        "event_type": "Recovery Write Off",
        "source_doctype": "NDIS Recovery Case",
        "accounting_treatment": "Future Controlled Write-off Journal",
        "allowed_target_doctype": "Journal Entry",
        "posting_route": "Future Controlled ERPNext Journal Entry",
        "design_status": "Active",
        "risk_level": "Critical",
        "journal_entry_allowed_later": 1,
        "xero_export_allowed_later": 1,
        "duplicate_prevention_rule": "One approved write-off posting per recovery case and claim line evidence set.",
        "failure_handling_rule": "If CFO sign-off or evidence is missing, block write-off posting.",
        "rollback_rule": "Future rollback must use a linked reversal JE, not delete submitted accounting records.",
        "design_notes": "High-risk design that should follow controlled Payment Entry sandbox design.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-PAYROLL-COST",
        "design_name": "AU Payroll Cost Import Duplication Prevention Design",
        "event_type": "Payroll Cost Import",
        "source_doctype": "NDIS Payroll Cost Import",
        "accounting_treatment": "Management Costing Only",
        "allowed_target_doctype": "None",
        "posting_route": "No Accounting Posting",
        "design_status": "Active",
        "risk_level": "Critical",
        "requires_reversal_plan": 0,
        "duplicate_prevention_rule": "NDIS Finance must never duplicate payroll accounting handled by AU Payroll / HRMS / ERPNext payroll.",
        "failure_handling_rule": "If source mapping is incomplete, block profitability allocation only.",
        "rollback_rule": "Cancel management cost import/allocation records only. Do not reverse payroll accounting here.",
        "design_notes": "Profitability costing only, not accounting posting.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-COST-POOL",
        "design_name": "NDIS Cost Pool Management-only Design",
        "event_type": "Cost Pool Allocation",
        "source_doctype": "NDIS Cost Pool",
        "accounting_treatment": "Management Costing Only",
        "allowed_target_doctype": "None",
        "posting_route": "No Accounting Posting",
        "design_status": "Active",
        "risk_level": "High",
        "requires_reversal_plan": 0,
        "duplicate_prevention_rule": "Cost pools are management allocation records and must not create accounting entries.",
        "failure_handling_rule": "If allocation basis is missing, block allocation/profitability reporting only.",
        "rollback_rule": "Cancel cost allocation records only. Do not touch GL.",
        "design_notes": "Accounting must originate from source bills, payroll or bank records, not management pools.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-GOVERNANCE",
        "design_name": "Governance Pack Non-posting Design",
        "event_type": "Governance Pack",
        "source_doctype": "NDIS Executive Governance Pack",
        "accounting_treatment": "Governance Evidence Only",
        "allowed_target_doctype": "None",
        "posting_route": "No Accounting Posting",
        "design_status": "Active",
        "risk_level": "Medium",
        "requires_cfo_approval": 0,
        "requires_duplicate_check": 0,
        "requires_reversal_plan": 0,
        "duplicate_prevention_rule": "Governance packs are evidence records only.",
        "failure_handling_rule": "If governance score is low, block future posting approval rather than posting from the pack.",
        "rollback_rule": "Cancel or revise governance records only.",
        "design_notes": "Governance supports approval; it never creates accounting.",
    },
    {
        "matrix_id": "NDIS-ACC-DESIGN-XERO-EXPORT",
        "design_name": "Future Xero Accounting Export Design Placeholder",
        "event_type": "Xero Export",
        "source_doctype": "NDIS Accounting Posting Request",
        "accounting_treatment": "Future External Export Only",
        "allowed_target_doctype": "External System",
        "posting_route": "Future Xero Connector",
        "design_status": "Draft",
        "risk_level": "High",
        "xero_export_allowed_later": 1,
        "duplicate_prevention_rule": "External Xero reference must be stored before any second export attempt is allowed.",
        "failure_handling_rule": "If export acknowledgement is missing or failed, keep request in exception status.",
        "rollback_rule": "Future rollback must use Xero void/reversal workflow and local sync status.",
        "design_notes": "Placeholder only. No Xero API or export is implemented in Phase 3A.",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_design_review_doctype()
    create_design_review_item_doctype()
    create_design_matrix_doctype()
    create_reports()
    seed_default_matrix()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Accounting Sandbox Completion Gate",
        "NDIS Accounting Sandbox Completion Gate Item",
        "NDIS Accounting Posting Policy",
        "NDIS Accounting Posting Request",
        "NDIS Sandbox Accounting Posting Run",
        "NDIS Sandbox Accounting Cleanup Run",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 3A requires completed Phase 2F. Missing DocTypes: {0}").format(", ".join(missing)))


def create_design_matrix_doctype():
    _create_doctype(
        name="NDIS Accounting Design Matrix",
        autoname="field:matrix_id",
        title_field="design_name",
        fields=[
            {"fieldname": "matrix_id", "label": "Matrix ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "design_name", "label": "Design Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "design_status", "label": "Design Status", "fieldtype": "Select", "options": "\nDraft\nActive\nSuspended\nRetired", "default": "Draft", "in_list_view": 1},
            {"fieldname": "risk_level", "label": "Risk Level", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Medium", "in_list_view": 1},
            {"fieldname": "scope_section", "label": "Event Scope", "fieldtype": "Section Break"},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Select", "options": "\nClaim Batch\nRemittance\nRecovery Receipt\nRecovery Write Off\nPayroll Cost Import\nCost Pool Allocation\nGovernance Pack\nXero Export\nOther", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType", "reqd": 1, "in_list_view": 1},
            {"fieldname": "accounting_treatment", "label": "Accounting Treatment", "fieldtype": "Select", "options": "\nReconcile Existing Sales Invoice\nFuture Controlled Payment Allocation\nFuture Controlled Payment Receipt\nFuture Controlled Write-off Journal\nManagement Costing Only\nGovernance Evidence Only\nFuture External Export Only\nNo Accounting Posting\nOther", "reqd": 1, "in_list_view": 1},
            {"fieldname": "allowed_target_doctype", "label": "Allowed Target DocType", "fieldtype": "Select", "options": "\nNone\nSales Invoice\nPayment Entry\nJournal Entry\nPurchase Invoice\nExternal System", "default": "None", "in_list_view": 1},
            {"fieldname": "posting_route", "label": "Posting Route", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "flags_section", "label": "Future Permission Flags", "fieldtype": "Section Break"},
            {"fieldname": "live_posting_allowed_later", "label": "Live Posting Allowed Later", "fieldtype": "Check", "default": "0"},
            {"fieldname": "direct_gl_allowed", "label": "Direct GL Allowed", "fieldtype": "Check", "default": "0"},
            {"fieldname": "payment_entry_allowed_later", "label": "Payment Entry Allowed Later", "fieldtype": "Check", "default": "0"},
            {"fieldname": "journal_entry_allowed_later", "label": "Journal Entry Allowed Later", "fieldtype": "Check", "default": "0"},
            {"fieldname": "sales_invoice_allowed_later", "label": "Sales Invoice Allowed Later", "fieldtype": "Check", "default": "0"},
            {"fieldname": "xero_export_allowed_later", "label": "Xero Export Allowed Later", "fieldtype": "Check", "default": "0"},
            {"fieldname": "controls_section", "label": "Control Requirements", "fieldtype": "Section Break"},
            {"fieldname": "requires_readiness_gate", "label": "Requires Readiness Gate", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_sandbox_completion_gate", "label": "Requires Sandbox Completion Gate", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_governance_pack", "label": "Requires Governance Pack", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_cfo_approval", "label": "Requires CFO Approval", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_duplicate_check", "label": "Requires Duplicate Check", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_reversal_plan", "label": "Requires Reversal Plan", "fieldtype": "Check", "default": "1"},
            {"fieldname": "rules_section", "label": "Rules", "fieldtype": "Section Break"},
            {"fieldname": "duplicate_prevention_rule", "label": "Duplicate Prevention Rule", "fieldtype": "Long Text"},
            {"fieldname": "failure_handling_rule", "label": "Failure Handling Rule", "fieldtype": "Long Text"},
            {"fieldname": "rollback_rule", "label": "Rollback / Undo Rule", "fieldtype": "Long Text"},
            {"fieldname": "design_notes", "label": "Design Notes", "fieldtype": "Long Text"},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "last_review", "label": "Last Review", "fieldtype": "Link", "options": "NDIS Accounting Design Review", "read_only": 1},
            {"fieldname": "last_review_on", "label": "Last Review On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "review_exception_count", "label": "Review Exception Count", "fieldtype": "Int", "read_only": 1},
        ],
    )


def create_design_review_doctype():
    _create_doctype(
        name="NDIS Accounting Design Review",
        autoname="field:review_id",
        title_field="review_id",
        fields=[
            {"fieldname": "review_id", "label": "Review ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "review_type", "label": "Review Type", "fieldtype": "Select", "options": "\nControlled Accounting Design Matrix\nPre Posting Adapter Design", "default": "Controlled Accounting Design Matrix", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPassed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "design_approved_for_next_phase", "label": "Design Approved For Next Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "reviewed_on", "label": "Reviewed On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "reviewed_by", "label": "Reviewed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_section", "label": "Summary", "fieldtype": "Section Break"},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "matrix_section", "label": "Matrix Evidence", "fieldtype": "Section Break"},
            {"fieldname": "matrix_count", "label": "Matrix Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "active_matrix_count", "label": "Active Matrix Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "draft_matrix_count", "label": "Draft Matrix Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "unsafe_matrix_count", "label": "Unsafe Matrix Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "policy_coverage_count", "label": "Policy Coverage Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "missing_policy_coverage_count", "label": "Missing Policy Coverage Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "completion_gate_section", "label": "Completion Gate Evidence", "fieldtype": "Section Break"},
            {"fieldname": "sandbox_completion_gate", "label": "Sandbox Completion Gate", "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "read_only": 1},
            {"fieldname": "sandbox_completion_allowed", "label": "Sandbox Completion Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "completion_score", "label": "Completion Score", "fieldtype": "Percent", "read_only": 1},
            {"fieldname": "ack_section", "label": "Acknowledgement", "fieldtype": "Section Break"},
            {"fieldname": "required_acknowledgement", "label": "Required Acknowledgement", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "acknowledgement", "label": "Acknowledgement", "fieldtype": "Data"},
            {"fieldname": "acknowledgement_ok", "label": "Acknowledgement OK", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "summary_json", "label": "Summary JSON", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "warning_log", "label": "Warning Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_design_review_item_doctype():
    _create_doctype(
        name="NDIS Accounting Design Review Item",
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "design_review", "label": "Design Review", "fieldtype": "Link", "options": "NDIS Accounting Design Review", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocker\nInfo\nCancelled", "default": "Info", "in_list_view": 1},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "\nLow\nMedium\nHigh\nCritical", "default": "Low", "in_list_view": 1},
            {"fieldname": "category", "label": "Category", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "check_key", "label": "Check Key", "fieldtype": "Data"},
            {"fieldname": "check_label", "label": "Check Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "source_doctype", "label": "Source DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "source_name", "label": "Source Name", "fieldtype": "Dynamic Link", "options": "source_doctype"},
            {"fieldname": "reviewed_on", "label": "Reviewed On", "fieldtype": "Datetime", "read_only": 1},
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


def seed_default_matrix():
    defaults = {
        "live_posting_allowed_later": 0,
        "direct_gl_allowed": 0,
        "payment_entry_allowed_later": 0,
        "journal_entry_allowed_later": 0,
        "sales_invoice_allowed_later": 0,
        "xero_export_allowed_later": 0,
        "requires_readiness_gate": 1,
        "requires_sandbox_completion_gate": 1,
        "requires_governance_pack": 1,
        "requires_cfo_approval": 1,
        "requires_duplicate_check": 1,
        "requires_reversal_plan": 1,
    }
    for row in DEFAULT_MATRIX:
        doc = frappe.get_doc("NDIS Accounting Design Matrix", row["matrix_id"]) if frappe.db.exists("NDIS Accounting Design Matrix", row["matrix_id"]) else frappe.new_doc("NDIS Accounting Design Matrix")
        doc.matrix_id = row["matrix_id"]
        for key, value in {**defaults, **row}.items():
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
        base.update({"read": 1, "write": 1, "create": 1, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1})
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
    if "Controlled Accounting Design" not in text_blob:
        content.append({"id": "ndis_controlled_accounting_design_heading", "type": "header", "data": {"text": "Controlled Accounting Design", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE3A_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "default_matrix": {row["matrix_id"]: bool(frappe.db.exists("NDIS Accounting Design Matrix", row["matrix_id"])) for row in DEFAULT_MATRIX},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE3A_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_accounting_design_matrix": permission_matrix().get("manage_accounting_design_matrix"),
            "run_accounting_design_review": permission_matrix().get("run_accounting_design_review"),
            "cancel_accounting_design_review": permission_matrix().get("cancel_accounting_design_review"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE3A_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE3A_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.accounting_design_matrix import quick_accounting_design_summary

        return callable(quick_accounting_design_summary)
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
