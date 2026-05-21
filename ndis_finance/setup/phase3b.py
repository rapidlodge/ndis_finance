import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


PHASE3B_DOCTYPES = [
    "NDIS Payment Entry Mapping Rule",
    "NDIS Payment Entry Allocation Preview",
    "NDIS Payment Entry Allocation Preview Line",
]

REPORTS = [
    {"report_name": "NDIS Payment Entry Mapping Rule Report", "ref_doctype": "NDIS Payment Entry Mapping Rule"},
    {"report_name": "NDIS Payment Entry Allocation Preview Report", "ref_doctype": "NDIS Payment Entry Allocation Preview"},
    {"report_name": "NDIS Payment Entry Allocation Exception Report", "ref_doctype": "NDIS Payment Entry Allocation Preview Line"},
]

REPORT_FILE_MAP = {
    "NDIS Payment Entry Mapping Rule Report": "ndis_payment_entry_mapping_rule_report",
    "NDIS Payment Entry Allocation Preview Report": "ndis_payment_entry_allocation_preview_report",
    "NDIS Payment Entry Allocation Exception Report": "ndis_payment_entry_allocation_exception_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    "NDIS Payment Entry Mapping Rule": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Payment Entry Allocation Preview": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Payment Entry Allocation Preview Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"

WORKSPACE_SHORTCUTS = [
    {"label": "Payment Entry Mapping Rules", "type": "DocType", "link_to": "NDIS Payment Entry Mapping Rule"},
    {"label": "Payment Entry Allocation Previews", "type": "DocType", "link_to": "NDIS Payment Entry Allocation Preview"},
    {"label": "Payment Entry Allocation Lines", "type": "DocType", "link_to": "NDIS Payment Entry Allocation Preview Line"},
    {"label": "Payment Entry Mapping Report", "type": "Report", "link_to": "NDIS Payment Entry Mapping Rule Report"},
    {"label": "Payment Entry Allocation Preview Report", "type": "Report", "link_to": "NDIS Payment Entry Allocation Preview Report"},
    {"label": "Payment Entry Allocation Exceptions", "type": "Report", "link_to": "NDIS Payment Entry Allocation Exception Report"},
]

DEFAULT_MAPPING_RULES = [
    {
        "mapping_id": "NDIS-PE-MAP-NDIA-DIRECT",
        "mapping_name": "NDIA Direct Remittance Mapping Placeholder",
        "payer_type": "NDIA",
        "mapping_scope": "NDIA Direct",
        "invoice_match_mode": "Matched Claim Line / Invoice Reference",
        "duplicate_key_policy": "Remittance Import + Remittance Line + Sales Invoice",
        "short_paid_handling": "Exclude And Route To Leakage",
        "rejected_handling": "Exclude And Route To Leakage",
        "design_notes": "Placeholder for future NDIA remittance-to-Payment Entry adapter. Phase 3B only previews allocation.",
        "rollback_rule": "Future rollback must cancel Payment Entry through ERPNext workflow and reopen allocation status.",
    },
    {
        "mapping_id": "NDIS-PE-MAP-PLAN-MANAGED",
        "mapping_name": "Plan Managed Receipt Mapping Placeholder",
        "payer_type": "Plan Manager",
        "mapping_scope": "Plan Managed",
        "invoice_match_mode": "Sales Invoice Reference",
        "duplicate_key_policy": "Payer + Receipt Reference + Sales Invoice",
        "short_paid_handling": "Exclude And Route To Recovery",
        "rejected_handling": "Exclude And Route To Recovery",
        "design_notes": "Placeholder for plan-managed receipts. No Payment Entry creation in Phase 3B.",
        "rollback_rule": "Future rollback must cancel Payment Entry and restore invoice allocation status.",
    },
    {
        "mapping_id": "NDIS-PE-MAP-SELF-MANAGED",
        "mapping_name": "Self Managed Receipt Mapping Placeholder",
        "payer_type": "Participant / Nominee",
        "mapping_scope": "Self Managed",
        "invoice_match_mode": "Sales Invoice Reference",
        "duplicate_key_policy": "Payer + Receipt Reference + Sales Invoice",
        "short_paid_handling": "Exclude And Route To Recovery",
        "rejected_handling": "Exclude And Route To Recovery",
        "design_notes": "Placeholder for self-managed receipts. No Payment Entry creation in Phase 3B.",
        "rollback_rule": "Future rollback must cancel Payment Entry and restore invoice allocation status.",
    },
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_mapping_rule_doctype()
    create_allocation_preview_doctype()
    create_allocation_preview_line_doctype()
    create_reports()
    seed_default_mapping_rules()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Accounting Design Matrix",
        "NDIS Accounting Design Review",
        "NDIS Accounting Sandbox Completion Gate",
        "NDIS Remittance Import",
        "NDIS Remittance Import Line",
        "Sales Invoice",
        "Payment Entry",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(_("Phase 3B requires Phase 3A, Phase 2F, remittance import and ERPNext accounting. Missing DocTypes: {0}").format(", ".join(missing)))


def create_mapping_rule_doctype():
    _create_doctype(
        name="NDIS Payment Entry Mapping Rule",
        autoname="field:mapping_id",
        title_field="mapping_name",
        fields=[
            {"fieldname": "mapping_id", "label": "Mapping ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "mapping_name", "label": "Mapping Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nActive\nSuspended\nRetired", "default": "Draft", "in_list_view": 1},
            {"fieldname": "scope_section", "label": "Scope", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "payer_type", "label": "Payer Type", "fieldtype": "Select", "options": "\nNDIA\nPlan Manager\nParticipant / Nominee\nOther", "default": "NDIA", "in_list_view": 1},
            {"fieldname": "payer_customer", "label": "Payer Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "mapping_scope", "label": "Mapping Scope", "fieldtype": "Data"},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "remittance_source_doctype", "label": "Remittance Source DocType", "fieldtype": "Link", "options": "DocType", "default": "NDIS Remittance Import", "in_list_view": 1},
            {"fieldname": "line_source_doctype", "label": "Line Source DocType", "fieldtype": "Link", "options": "DocType", "default": "NDIS Remittance Import Line"},
            {"fieldname": "invoice_match_mode", "label": "Invoice Match Mode", "fieldtype": "Select", "options": "\nMatched Claim Line / Invoice Reference\nSales Invoice Reference\nInvoice Number Text Match\nManual Review Only", "default": "Matched Claim Line / Invoice Reference"},
            {"fieldname": "duplicate_key_policy", "label": "Duplicate Key Policy", "fieldtype": "Data"},
            {"fieldname": "accounting_section", "label": "Future Payment Entry Mapping", "fieldtype": "Section Break"},
            {"fieldname": "payment_type", "label": "Payment Type", "fieldtype": "Select", "options": "\nReceive\nPay", "default": "Receive"},
            {"fieldname": "mode_of_payment", "label": "Mode of Payment", "fieldtype": "Link", "options": "Mode of Payment"},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "default_cost_center", "label": "Default Cost Center", "fieldtype": "Link", "options": "Cost Center"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_creation_allowed", "label": "Payment Entry Creation Allowed", "fieldtype": "Check", "default": "0", "read_only": 1},
            {"fieldname": "requires_design_review", "label": "Requires Design Review", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_sandbox_completion_gate", "label": "Requires Sandbox Completion Gate", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_cfo_approval", "label": "Requires CFO Approval", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_bank_account_mapping", "label": "Requires Bank Account Mapping", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_receivable_account_mapping", "label": "Requires Receivable Account Mapping", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_duplicate_check", "label": "Requires Duplicate Check", "fieldtype": "Check", "default": "1"},
            {"fieldname": "requires_rollback_plan", "label": "Requires Rollback Plan", "fieldtype": "Check", "default": "1"},
            {"fieldname": "exception_section", "label": "Exception Handling", "fieldtype": "Section Break"},
            {"fieldname": "short_paid_handling", "label": "Short-paid Handling", "fieldtype": "Select", "options": "\nExclude And Route To Leakage\nExclude And Route To Recovery\nManual Review\nAllow Partial Allocation Later", "default": "Exclude And Route To Leakage"},
            {"fieldname": "rejected_handling", "label": "Rejected Handling", "fieldtype": "Select", "options": "\nExclude And Route To Leakage\nExclude And Route To Recovery\nManual Review", "default": "Exclude And Route To Leakage"},
            {"fieldname": "unallocated_handling", "label": "Unallocated Handling", "fieldtype": "Select", "options": "\nHold As Exception\nFuture Unallocated Payment\nManual Review", "default": "Hold As Exception"},
            {"fieldname": "overpayment_handling", "label": "Overpayment Handling", "fieldtype": "Select", "options": "\nHold As Exception\nFuture Unallocated Payment\nManual Review", "default": "Hold As Exception"},
            {"fieldname": "notes_section", "label": "Design Notes", "fieldtype": "Section Break"},
            {"fieldname": "design_notes", "label": "Design Notes", "fieldtype": "Long Text"},
            {"fieldname": "rollback_rule", "label": "Rollback Rule", "fieldtype": "Long Text"},
            {"fieldname": "last_preview", "label": "Last Allocation Preview", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "last_preview_on", "label": "Last Preview On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "preview_count", "label": "Preview Count", "fieldtype": "Int", "read_only": 1},
        ],
    )


def create_allocation_preview_doctype():
    _create_doctype(
        name="NDIS Payment Entry Allocation Preview",
        autoname="field:preview_id",
        title_field="preview_id",
        fields=[
            {"fieldname": "preview_id", "label": "Preview ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "validation_status", "label": "Validation Status", "fieldtype": "Select", "options": "\nPass\nWarning\nBlocked", "default": "Warning", "in_list_view": 1},
            {"fieldname": "source_section", "label": "Source", "fieldtype": "Section Break"},
            {"fieldname": "mapping_rule", "label": "Mapping Rule", "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "reqd": 1, "in_list_view": 1},
            {"fieldname": "remittance_import", "label": "Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import", "reqd": 1, "in_list_view": 1},
            {"fieldname": "source_status", "label": "Source Status", "fieldtype": "Data"},
            {"fieldname": "source_summary", "label": "Source Summary", "fieldtype": "Small Text"},
            {"fieldname": "control_section", "label": "Controls", "fieldtype": "Section Break"},
            {"fieldname": "sandbox_completion_gate", "label": "Sandbox Completion Gate", "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "read_only": 1},
            {"fieldname": "sandbox_completion_allowed", "label": "Sandbox Completion Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "design_review", "label": "Design Review", "fieldtype": "Link", "options": "NDIS Accounting Design Review", "read_only": 1},
            {"fieldname": "design_approved", "label": "Design Approved", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "payment_entry_creation_allowed", "label": "Payment Entry Creation Allowed", "fieldtype": "Check", "default": "0", "read_only": 1},
            {"fieldname": "preview_only_confirmation", "label": "Preview Only Confirmation", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "mapping_section", "label": "Future Payment Entry Mapping", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "payer_type", "label": "Payer Type", "fieldtype": "Data"},
            {"fieldname": "payer_customer", "label": "Payer Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "payment_type", "label": "Payment Type", "fieldtype": "Data"},
            {"fieldname": "mode_of_payment", "label": "Mode of Payment", "fieldtype": "Link", "options": "Mode of Payment"},
            {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "receivable_account", "label": "Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
            {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "options": "Currency"},
            {"fieldname": "summary_section", "label": "Preview Summary", "fieldtype": "Section Break"},
            {"fieldname": "total_receipt_amount", "label": "Total Receipt Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "allocatable_amount", "label": "Allocatable Amount", "fieldtype": "Currency", "read_only": 1, "in_list_view": 1},
            {"fieldname": "exception_amount", "label": "Exception Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "unmatched_amount", "label": "Unmatched Amount", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "line_count", "label": "Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "allocatable_line_count", "label": "Allocatable Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "exception_line_count", "label": "Exception Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "duplicate_line_count", "label": "Duplicate Line Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "created_on", "label": "Created On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "created_by_user", "label": "Created By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "cancelled_on", "label": "Cancelled On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "cancelled_by", "label": "Cancelled By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "validation_log", "label": "Validation Log", "fieldtype": "Long Text", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_allocation_preview_line_doctype():
    _create_doctype(
        name="NDIS Payment Entry Allocation Preview Line",
        autoname="hash",
        title_field="line_label",
        fields=[
            {"fieldname": "allocation_preview", "label": "Allocation Preview", "fieldtype": "Link", "options": "NDIS Payment Entry Allocation Preview", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nAllocatable\nException\nDuplicate\nExcluded\nCancelled", "default": "Exception", "in_list_view": 1},
            {"fieldname": "line_no", "label": "Line No", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "line_label", "label": "Line Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "remittance_line", "label": "Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line"},
            {"fieldname": "claim_line", "label": "Claim Line", "fieldtype": "Data"},
            {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice"},
            {"fieldname": "invoice_status", "label": "Invoice Status", "fieldtype": "Data"},
            {"fieldname": "receipt_amount", "label": "Receipt Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "invoice_outstanding_amount", "label": "Invoice Outstanding Amount", "fieldtype": "Currency"},
            {"fieldname": "allocation_amount", "label": "Allocation Amount", "fieldtype": "Currency", "in_list_view": 1},
            {"fieldname": "exception_amount", "label": "Exception Amount", "fieldtype": "Currency"},
            {"fieldname": "outcome_status", "label": "Outcome Status", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "allocation_decision", "label": "Allocation Decision", "fieldtype": "Data"},
            {"fieldname": "duplicate_key", "label": "Duplicate Key", "fieldtype": "Data"},
            {"fieldname": "duplicate_detected", "label": "Duplicate Detected", "fieldtype": "Check"},
            {"fieldname": "block_reason", "label": "Block Reason", "fieldtype": "Small Text"},
            {"fieldname": "recommendation", "label": "Recommendation", "fieldtype": "Small Text"},
            {"fieldname": "future_payment_entry_reference", "label": "Future Payment Entry Reference", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "preview_only_note", "label": "Preview Only Note", "fieldtype": "Small Text", "read_only": 1},
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


def seed_default_mapping_rules():
    defaults = {
        "status": "Draft",
        "remittance_source_doctype": "NDIS Remittance Import",
        "line_source_doctype": "NDIS Remittance Import Line",
        "payment_type": "Receive",
        "payment_entry_creation_allowed": 0,
        "requires_design_review": 1,
        "requires_sandbox_completion_gate": 1,
        "requires_cfo_approval": 1,
        "requires_bank_account_mapping": 1,
        "requires_receivable_account_mapping": 1,
        "requires_duplicate_check": 1,
        "requires_rollback_plan": 1,
        "unallocated_handling": "Hold As Exception",
        "overpayment_handling": "Hold As Exception",
    }
    for row in DEFAULT_MAPPING_RULES:
        doc = frappe.get_doc("NDIS Payment Entry Mapping Rule", row["mapping_id"]) if frappe.db.exists("NDIS Payment Entry Mapping Rule", row["mapping_id"]) else frappe.new_doc("NDIS Payment Entry Mapping Rule")
        doc.mapping_id = row["mapping_id"]
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
    elif profile == "create_write_read_report":
        base.update({"read": 1, "write": 1, "create": 1, "report": 1, "export": 1, "print": 1, "email": 1})
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
    if "Payment Entry Sandbox Design" not in text_blob:
        content.append({"id": "ndis_payment_entry_sandbox_design_heading", "type": "header", "data": {"text": "Payment Entry Sandbox Design", "col": 12}})
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE3B_DOCTYPES},
        "reports": {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS},
        "default_mapping_rules": {row["mapping_id"]: bool(frappe.db.exists("NDIS Payment Entry Mapping Rule", row["mapping_id"])) for row in DEFAULT_MAPPING_RULES},
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE3B_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_payment_entry_mapping_rule": permission_matrix().get("manage_payment_entry_mapping_rule"),
            "run_payment_entry_allocation_preview": permission_matrix().get("run_payment_entry_allocation_preview"),
            "cancel_payment_entry_allocation_preview": permission_matrix().get("cancel_payment_entry_allocation_preview"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE3B_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE3B_DOCTYPES},
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "report_files": check_report_files(),
    }


def can_import_service():
    try:
        from ndis_finance.services.payment_entry_sandbox_design import quick_payment_entry_design_summary

        return callable(quick_payment_entry_design_summary)
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
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            result[shortcut["label"]] = True
    return result
