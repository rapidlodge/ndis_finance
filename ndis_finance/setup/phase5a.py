import json
import os

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


POLICY_DOCTYPE = "NDIS PE Production Posting Policy"
GATE_DOCTYPE = "NDIS PE Production Design Gate"
GATE_ITEM_DOCTYPE = "NDIS PE Production Design Gate Item"

PHASE5A_DOCTYPES = [POLICY_DOCTYPE, GATE_DOCTYPE, GATE_ITEM_DOCTYPE]

REPORTS = [
    {"report_name": "NDIS PE Production Policy Register", "ref_doctype": POLICY_DOCTYPE},
    {"report_name": "NDIS PE Production Design Gate Report", "ref_doctype": GATE_DOCTYPE},
    {"report_name": "NDIS PE Production Design Exception Report", "ref_doctype": GATE_ITEM_DOCTYPE},
]

REPORT_FILE_MAP = {
    "NDIS PE Production Policy Register": "ndis_pe_production_policy_register",
    "NDIS PE Production Design Gate Report": "ndis_pe_production_design_gate_report",
    "NDIS PE Production Design Exception Report": "ndis_pe_production_design_exception_report",
}

REPORT_ROLES = ["System Manager", "NDIS CFO", "NDIS Finance Manager", "NDIS Finance Officer", "NDIS Finance Read Only"]

DOC_PERM_MATRIX = {
    POLICY_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "full",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    GATE_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    GATE_ITEM_DOCTYPE: {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
}

WORKSPACE_NAME = "NDIS Finance"
WORKSPACE_SHORTCUTS = [
    {"label": "PE Production Posting Policies", "type": "DocType", "link_to": POLICY_DOCTYPE},
    {"label": "PE Production Design Gates", "type": "DocType", "link_to": GATE_DOCTYPE},
    {"label": "PE Production Policy Register", "type": "Report", "link_to": "NDIS PE Production Policy Register"},
    {"label": "PE Production Design Exceptions", "type": "Report", "link_to": "NDIS PE Production Design Exception Report"},
]

DEFAULT_POLICIES = [
    ("NDIS-PE-POLICY-PAID-CLAIM", "Paid Claim - NDIA Direct Receipt", "Paid Claim", "Paid", "Eligible After Approval", "Design Only - Live Posting Blocked", "NDIS-PE-MAP-NDIA-DIRECT", "One Payment Entry Per Sales Invoice Allocation", "Allow Full Payment Only", "CFO Approval Required", "Design Approved"),
    ("NDIS-PE-POLICY-SHORT-PAID", "Short Paid Claim - Partial Receipt + Shortfall", "Short Paid Claim", "Short Paid", "Eligible After Approval", "Design Only - Live Posting Blocked", "NDIS-PE-MAP-NDIA-DIRECT", "One Payment Entry Per Sales Invoice Allocation", "Allow Partial Payment And Preserve Shortfall", "CFO Approval Required", "Design Approved"),
    ("NDIS-PE-POLICY-REJECTED", "Rejected Claim - No Payment Entry", "Rejected Claim", "Rejected", "Never Post Payment Entry", "Blocked", "", "No Payment Entry Allowed", "No Receipt", "System Block", "Design Approved"),
    ("NDIS-PE-POLICY-WRITE-OFF", "Write-off / Do Not Recover - No Payment Entry", "Write Off", "Written Off", "Never Post Payment Entry", "Blocked", "", "No Payment Entry Allowed", "No Receipt", "Write-off Approval Required", "Design Approved"),
    ("NDIS-PE-POLICY-CANCELLED", "Cancelled Claim / Cancelled Invoice - No Payment Entry", "Cancelled Claim", "Cancelled", "Never Post Payment Entry", "Blocked", "", "No Payment Entry Allowed", "No Receipt", "System Block", "Design Approved"),
    ("NDIS-PE-POLICY-MANUAL-OVERRIDE", "Manual Override - CFO Controlled Only", "Manual Override", "Manual", "Eligible After Approval", "Design Only - Live Posting Blocked", "", "Manual Duplicate Review Required", "Manual Review Required", "CFO Approval Required", "Needs Review"),
    ("NDIS-PE-POLICY-XERO", "Xero Export - Placeholder Only", "Xero Export", "Export", "Never Post Payment Entry", "Placeholder Only", "", "No ERPNext Payment Entry From Xero Placeholder", "Not Applicable", "Future Design Required", "Inactive"),
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_policy_doctype()
    create_gate_doctype()
    create_gate_item_doctype()
    create_reports()
    seed_default_policies()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS PE Sandbox Readiness Freeze",
        "NDIS PE Sandbox Readiness Freeze Item",
        "NDIS Payment Entry Allocation Preview",
        "NDIS Sandbox Payment Entry Run",
        "NDIS Invoice Backed PE Smoke Run",
        "NDIS Sandbox Accounting Cleanup Pack",
        "NDIS Payment Entry Sandbox Completion Gate",
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
        frappe.throw(_("Phase 5A requires completed Phase 4D and Payment Entry sandbox chain. Missing: {0}").format(", ".join(missing)))


def create_policy_doctype():
    _create_doctype(
        name=POLICY_DOCTYPE,
        autoname="field:policy_id",
        title_field="policy_name",
        fields=[
            {"fieldname": "policy_id", "label": "Policy ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "policy_name", "label": "Policy Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "policy_status", "label": "Policy Status", "fieldtype": "Select", "options": "\nDraft\nDesign Approved\nNeeds Review\nBlocked\nInactive", "default": "Draft", "in_list_view": 1},
            {"fieldname": "production_posting_enabled", "label": "Production Posting Enabled", "fieldtype": "Check", "default": "0", "in_list_view": 1},
            {"fieldname": "posting_mode", "label": "Posting Mode", "fieldtype": "Select", "options": "\nDesign Only - Live Posting Blocked\nBlocked\nPlaceholder Only\nFuture Design Required", "default": "Design Only - Live Posting Blocked", "in_list_view": 1},
            {"fieldname": "rule_section", "label": "Rule", "fieldtype": "Section Break"},
            {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Select", "options": "\nPaid Claim\nShort Paid Claim\nRejected Claim\nWrite Off\nCancelled Claim\nManual Override\nXero Export", "in_list_view": 1},
            {"fieldname": "claim_outcome", "label": "Claim Outcome", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "posting_decision", "label": "Posting Decision", "fieldtype": "Select", "options": "\nEligible After Approval\nNever Post Payment Entry\nManual Review Required", "in_list_view": 1},
            {"fieldname": "mapping_rule", "label": "Mapping Rule", "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule"},
            {"fieldname": "duplicate_policy", "label": "Duplicate Policy", "fieldtype": "Select", "options": "\nOne Payment Entry Per Sales Invoice Allocation\nNo Payment Entry Allowed\nManual Duplicate Review Required\nNo ERPNext Payment Entry From Xero Placeholder"},
            {"fieldname": "partial_payment_handling", "label": "Partial Payment Handling", "fieldtype": "Select", "options": "\nAllow Full Payment Only\nAllow Partial Payment And Preserve Shortfall\nNo Receipt\nManual Review Required\nNot Applicable"},
            {"fieldname": "approval_level", "label": "Approval Level", "fieldtype": "Select", "options": "\nCFO Approval Required\nWrite-off Approval Required\nSystem Block\nFuture Design Required"},
            {"fieldname": "account_section", "label": "Account Controls", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company"},
            {"fieldname": "allowed_bank_account", "label": "Allowed Bank Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allowed_receivable_account", "label": "Allowed Receivable Account", "fieldtype": "Link", "options": "Account"},
            {"fieldname": "allow_cross_company_posting", "label": "Allow Cross-company Posting", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_overpayment", "label": "Allow Overpayment", "fieldtype": "Check", "default": "0"},
            {"fieldname": "allow_negative_receipt", "label": "Allow Negative Receipt", "fieldtype": "Check", "default": "0"},
            {"fieldname": "audit_section", "label": "Audit", "fieldtype": "Section Break"},
            {"fieldname": "seeded_by_phase", "label": "Seeded By Phase", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "last_reviewed_on", "label": "Last Reviewed On", "fieldtype": "Datetime", "read_only": 1},
            {"fieldname": "last_reviewed_by", "label": "Last Reviewed By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
        ],
    )


def create_gate_doctype():
    _create_doctype(
        name=GATE_DOCTYPE,
        autoname="field:gate_id",
        title_field="gate_id",
        fields=[
            {"fieldname": "gate_id", "label": "Gate ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nDesign Approved\nNeeds Review\nBlocked\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "gate_type", "label": "Gate Type", "fieldtype": "Select", "options": "\nProduction Payment Entry Posting Design\nPre-Live Payment Entry Activation", "default": "Production Payment Entry Posting Design", "in_list_view": 1},
            {"fieldname": "design_approved_for_next_phase", "label": "Design Approved For Next Phase", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "live_posting_allowed", "label": "Live Posting Allowed", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "score_section", "label": "Design Score", "fieldtype": "Section Break"},
            {"fieldname": "design_score", "label": "Design Score", "fieldtype": "Percent", "read_only": 1, "in_list_view": 1},
            {"fieldname": "design_status", "label": "Design Status", "fieldtype": "Select", "options": "\nReady For Controlled Activation Design\nReady With Warnings\nNeeds Review\nBlocked", "read_only": 1, "in_list_view": 1},
            {"fieldname": "blocker_count", "label": "Blocker Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "warning_count", "label": "Warning Count", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "pass_count", "label": "Pass Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "info_count", "label": "Info Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "item_count", "label": "Item Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "policy_section", "label": "Policy Evidence", "fieldtype": "Section Break"},
            {"fieldname": "policy_count", "label": "Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "design_approved_policy_count", "label": "Design Approved Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "needs_review_policy_count", "label": "Needs Review Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "blocked_policy_count", "label": "Blocked Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "live_enabled_policy_count", "label": "Live Enabled Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "paid_policy_count", "label": "Paid Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "short_paid_policy_count", "label": "Short-paid Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "rejected_block_policy_count", "label": "Rejected Block Policy Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "readiness_section", "label": "Readiness Evidence", "fieldtype": "Section Break"},
            {"fieldname": "phase4d_freeze_count", "label": "Phase 4D Freeze Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "phase4d_ready_count", "label": "Phase 4D Ready Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "invoice_backed_smoke_count", "label": "Invoice-backed Smoke Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "cleanup_pack_count", "label": "Cleanup Pack Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Strict Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "draft_sandbox_pe_count", "label": "Draft Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_sandbox_pe_count", "label": "Submitted Sandbox PE Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count", "label": "Payment Entry GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_payment_entry_count_today", "label": "Submitted PE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "purchase_invoice_count_today", "label": "Purchase Invoice Count Today", "fieldtype": "Int", "read_only": 1},
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


def create_gate_item_doctype():
    _create_doctype(
        name=GATE_ITEM_DOCTYPE,
        autoname="hash",
        title_field="check_label",
        fields=[
            {"fieldname": "design_gate", "label": "Design Gate", "fieldtype": "Link", "options": GATE_DOCTYPE, "reqd": 1, "in_list_view": 1},
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


def seed_default_policies():
    notes = {
        "NDIS-PE-POLICY-PAID-CLAIM": "Standard fully paid NDIA/direct remittance outcome. Live posting remains blocked until later production activation phase.",
        "NDIS-PE-POLICY-SHORT-PAID": "Receipt can be posted only for actual paid amount; shortfall must remain in recovery/leakage workflow.",
        "NDIS-PE-POLICY-REJECTED": "Rejected claims must not create Payment Entry. They stay in leakage/recovery workflow.",
        "NDIS-PE-POLICY-WRITE-OFF": "Write-off is not a bank receipt. Any write-off accounting must be handled separately.",
        "NDIS-PE-POLICY-CANCELLED": "Cancelled claims or invoices must not create Payment Entries.",
        "NDIS-PE-POLICY-MANUAL-OVERRIDE": "Manual override requires extra governance before any live posting phase.",
        "NDIS-PE-POLICY-XERO": "Xero is intentionally not part of live Payment Entry posting yet.",
    }
    for policy in DEFAULT_POLICIES:
        (
            policy_id,
            policy_name,
            event_type,
            outcome,
            decision,
            mode,
            mapping_rule,
            duplicate_policy,
            partial_handling,
            approval,
            status,
        ) = policy
        existing = frappe.db.exists(POLICY_DOCTYPE, policy_id)
        doc = frappe.get_doc(POLICY_DOCTYPE, existing) if existing else frappe.new_doc(POLICY_DOCTYPE)
        doc.policy_id = policy_id
        doc.policy_name = policy_name
        doc.event_type = event_type
        doc.claim_outcome = outcome
        doc.posting_decision = decision
        doc.posting_mode = mode
        doc.mapping_rule = mapping_rule if mapping_rule and frappe.db.exists("NDIS Payment Entry Mapping Rule", mapping_rule) else None
        doc.duplicate_policy = duplicate_policy
        doc.partial_payment_handling = partial_handling
        doc.approval_level = approval
        doc.policy_status = status
        doc.production_posting_enabled = 0
        doc.seeded_by_phase = "Phase 5A"
        doc.notes = notes.get(policy_id)
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
    if "Production Payment Entry Design" not in text_blob:
        content.append({"id": "ndis_pe_production_design_heading", "type": "header", "data": {"text": "Production Payment Entry Design", "col": 12}})
    for shortcut in WORKSPACE_SHORTCUTS:
        if shortcut["label"] in text_blob or shortcut["link_to"] in text_blob:
            continue
        content.append({"id": frappe.scrub(shortcut["label"]), "type": "shortcut", "data": {"label": shortcut["label"], "link_to": shortcut["link_to"], "type": shortcut["type"], "col": 3}})
    ws.content = json.dumps(content)


@frappe.whitelist()
def health_check():
    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE5A_DOCTYPES}
    reports = {report["report_name"]: bool(frappe.db.exists("Report", report["report_name"])) for report in REPORTS}
    policy_count = count(POLICY_DOCTYPE)
    live_enabled_policy_count = count(POLICY_DOCTYPE, {"production_posting_enabled": 1})
    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})
    doc_events = hooks.get("doc_events", {}) or {}
    pe_events_blob = json.dumps(doc_events.get("Payment Entry", {}), default=str)
    si_events_blob = json.dumps(doc_events.get("Sales Invoice", {}), default=str)
    return {
        "doctypes": doctypes,
        "reports": reports,
        "policy_count": policy_count,
        "live_enabled_policy_count": live_enabled_policy_count,
        "permissions": {
            dt: frappe.get_all("DocPerm", filters={"parent": dt}, fields=["role", "read", "write", "create", "delete", "report", "export"], order_by="role asc")
            for dt in PHASE5A_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "manage_pe_production_posting_policy": permission_matrix().get("manage_pe_production_posting_policy"),
            "run_pe_production_design_gate": permission_matrix().get("run_pe_production_design_gate"),
            "cancel_pe_production_design_gate": permission_matrix().get("cancel_pe_production_design_gate"),
        },
        "js_hooks": {dt: dt in doctype_js for dt in PHASE5A_DOCTYPES},
        "list_js_hooks": {dt: dt in doctype_list_js for dt in PHASE5A_DOCTYPES},
        "payment_entry_submit_blocker_still_registered": "block_sandbox_payment_entry_submit" in pe_events_blob,
        "sales_invoice_submit_safety_still_registered": "block_unacknowledged_sandbox_sales_invoice_submit" in si_events_blob,
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
        "report_files": check_report_files(),
    }


def count(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def can_import_service():
    try:
        from ndis_finance.services.pe_production_design_gate import quick_pe_production_design_summary

        return callable(quick_pe_production_design_summary)
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
