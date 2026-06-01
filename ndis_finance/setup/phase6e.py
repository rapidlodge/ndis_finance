import json
from pathlib import Path

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE, _create_doctype
from ndis_finance.services.permissions import permission_matrix


RUN_DOCTYPE = "NDIS Real Remittance PE Source Harness Run"
LINE_DOCTYPE = "NDIS Real Remittance PE Source Harness Line"
PHASE6E_DOCTYPES = [RUN_DOCTYPE, LINE_DOCTYPE]

REPORTS = [
    {
        "report_name": "NDIS Real Remittance PE Source Harness Report",
        "ref_doctype": RUN_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_source_harness_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Source Harness Line Report",
        "ref_doctype": LINE_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_source_harness_line_report",
    },
    {
        "report_name": "NDIS Real Remittance PE Source Harness Readiness Report",
        "ref_doctype": RUN_DOCTYPE,
        "module_path": "ndis_real_remittance_pe_source_harness_readiness_report",
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
    {"label": "Real Remittance PE Source Harness Runs", "type": "DocType", "link_to": RUN_DOCTYPE},
    {"label": "Real Remittance PE Source Harness Lines", "type": "DocType", "link_to": LINE_DOCTYPE},
    {
        "label": "Real Remittance PE Source Harness Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Source Harness Report",
    },
    {
        "label": "Real Remittance PE Source Harness Line Report",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Source Harness Line Report",
    },
    {
        "label": "Real Remittance PE Source Harness Readiness",
        "type": "Report",
        "link_to": "NDIS Real Remittance PE Source Harness Readiness Report",
    },
]

CUSTOM_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_invoice",
            "label": "NDIS Real Remittance PE Harness Invoice",
            "fieldtype": "Check",
            "insert_after": "customer",
        },
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_run",
            "label": "NDIS Real Remittance PE Harness Run",
            "fieldtype": "Link",
            "options": RUN_DOCTYPE,
            "insert_after": "custom_ndis_real_remittance_pe_harness_invoice",
        },
    ],
    "NDIS Claim Line": [
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_source",
            "label": "NDIS Real Remittance PE Harness Source",
            "fieldtype": "Check",
            "insert_after": None,
        },
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_run",
            "label": "NDIS Real Remittance PE Harness Run",
            "fieldtype": "Link",
            "options": RUN_DOCTYPE,
            "insert_after": "custom_ndis_real_remittance_pe_harness_source",
        },
    ],
    "NDIS Remittance Import": [
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_source",
            "label": "NDIS Real Remittance PE Harness Source",
            "fieldtype": "Check",
            "insert_after": None,
        },
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_run",
            "label": "NDIS Real Remittance PE Harness Run",
            "fieldtype": "Link",
            "options": RUN_DOCTYPE,
            "insert_after": "custom_ndis_real_remittance_pe_harness_source",
        },
    ],
    "NDIS Remittance Import Line": [
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_source",
            "label": "NDIS Real Remittance PE Harness Source",
            "fieldtype": "Check",
            "insert_after": None,
        },
        {
            "fieldname": "custom_ndis_real_remittance_pe_harness_run",
            "label": "NDIS Real Remittance PE Harness Run",
            "fieldtype": "Link",
            "options": RUN_DOCTYPE,
            "insert_after": "custom_ndis_real_remittance_pe_harness_source",
        },
    ],
}


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_harness_run_doctype()
    create_harness_line_doctype()
    create_custom_fields()
    create_reports()
    harden_permissions()
    add_workspace_shortcuts()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = [
        "NDIS Real Remittance PE Activation Gate",
        "NDIS Real Remittance PE Adapter Run",
        "NDIS Real Remittance PE Preview",
        "NDIS Real Remittance PE Design Gate",
        "NDIS Remittance Import",
        "NDIS Remittance Import Line",
        "NDIS Claim Line",
        "Sales Invoice",
        "Sales Invoice Item",
        "Payment Entry",
        "GL Entry",
        "Customer",
        "Item",
        "Report",
        "Workspace",
    ]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("Phase 6E requires completed Phase 6D and remittance foundation. Missing: {0}").format(
                ", ".join(missing)
            )
        )


def create_harness_run_doctype():
    _create_doctype(
        name=RUN_DOCTYPE,
        autoname="field:harness_run_id",
        title_field="harness_run_id",
        fields=[
            {"fieldname": "harness_run_id", "label": "Harness Run ID", "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPreviewed\nNeeds Review\nSource Created\nSource Ready\nCancelled", "default": "Draft", "in_list_view": 1},
            {"fieldname": "harness_type", "label": "Harness Type", "fieldtype": "Select", "options": "\nControlled Eligible Real Remittance Source\nSource Harness Only", "default": "Controlled Eligible Real Remittance Source", "in_list_view": 1},
            {"fieldname": "source_ready_for_preview", "label": "Source Ready For Preview", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "real_posting_allowed", "label": "Real Posting Allowed", "fieldtype": "Check", "read_only": 1, "in_list_view": 1},
            {"fieldname": "source_section", "label": "Controlled Source", "fieldtype": "Section Break"},
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "in_list_view": 1},
            {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer"},
            {"fieldname": "item", "label": "Item", "fieldtype": "Link", "options": "Item"},
            {"fieldname": "sales_invoice", "label": "Controlled Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "in_list_view": 1},
            {"fieldname": "claim_line", "label": "Controlled Claim Line", "fieldtype": "Link", "options": "NDIS Claim Line"},
            {"fieldname": "remittance_import", "label": "Controlled Remittance Import", "fieldtype": "Link", "options": "NDIS Remittance Import", "in_list_view": 1},
            {"fieldname": "remittance_line", "label": "Controlled Remittance Line", "fieldtype": "Link", "options": "NDIS Remittance Import Line", "in_list_view": 1},
            {"fieldname": "amount_section", "label": "Amount", "fieldtype": "Section Break"},
            {"fieldname": "source_amount", "label": "Source Amount", "fieldtype": "Currency", "default": 1},
            {"fieldname": "invoice_outstanding_before_payment", "label": "Invoice Outstanding Before Payment", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "sales_invoice_gl_count", "label": "Sales Invoice GL Count", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "sales_invoice_gl_net", "label": "Sales Invoice GL Net", "fieldtype": "Currency", "read_only": 1},
            {"fieldname": "follow_section", "label": "Expected Follow-through", "fieldtype": "Section Break"},
            {"fieldname": "expected_phase6b_eligible_lines", "label": "Expected Phase 6B Eligible Lines", "fieldtype": "Int", "default": 1},
            {"fieldname": "expected_phase6c_would_create_pe", "label": "Expected Phase 6C Would Create PE", "fieldtype": "Int", "default": 1},
            {"fieldname": "expected_phase6d_ready_for_smoke", "label": "Expected Phase 6D Ready For Smoke", "fieldtype": "Check", "default": 1},
            {"fieldname": "site_section", "label": "Site / Config", "fieldtype": "Section Break"},
            {"fieldname": "site_name", "label": "Site Name", "fieldtype": "Data", "read_only": 1},
            {"fieldname": "sandbox_config_enabled", "label": "Sandbox Config Enabled", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "production_mode_detected", "label": "Production Mode Detected", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "live_payment_entry_posting_config", "label": "Live PE Posting Config", "fieldtype": "Check", "read_only": 1},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1, "in_list_view": 1},
            {"fieldname": "checked_by", "label": "Checked By", "fieldtype": "Link", "options": "User", "read_only": 1},
            {"fieldname": "guardrail_section", "label": "Movement Guardrails", "fieldtype": "Section Break"},
            {"fieldname": "payment_entry_count_before", "label": "Payment Entry Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_count_after", "label": "Payment Entry Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_before", "label": "Payment Entry GL Count Before", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "payment_entry_gl_count_after", "label": "Payment Entry GL Count After", "fieldtype": "Int", "read_only": 1},
            {"fieldname": "submitted_journal_entry_count_today", "label": "Submitted JE Count Today", "fieldtype": "Int", "read_only": 1},
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


def create_harness_line_doctype():
    _create_doctype(
        name=LINE_DOCTYPE,
        autoname="hash",
        title_field="record_label",
        fields=[
            {"fieldname": "harness_run", "label": "Harness Run", "fieldtype": "Link", "options": RUN_DOCTYPE, "reqd": 1, "in_list_view": 1},
            {"fieldname": "record_type", "label": "Record Type", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "record_doctype", "label": "Record DocType", "fieldtype": "Link", "options": "DocType"},
            {"fieldname": "record_name", "label": "Record Name", "fieldtype": "Dynamic Link", "options": "record_doctype", "in_list_view": 1},
            {"fieldname": "record_label", "label": "Record Label", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nCreated\nSubmitted\nLinked\nSkipped\nCancelled\nInfo", "default": "Info", "in_list_view": 1},
            {"fieldname": "amount", "label": "Amount", "fieldtype": "Currency"},
            {"fieldname": "detail", "label": "Detail", "fieldtype": "Small Text"},
            {"fieldname": "checked_on", "label": "Checked On", "fieldtype": "Datetime", "read_only": 1},
        ],
    )


def create_custom_fields():
    for dt, field_list in CUSTOM_FIELDS.items():
        if not frappe.db.exists("DocType", dt):
            continue
        for field in field_list:
            ensure_custom_field(dt, field)


def ensure_custom_field(dt, field):
    if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": field["fieldname"]}):
        return
    doc = frappe.new_doc("Custom Field")
    doc.dt = dt
    doc.fieldname = field["fieldname"]
    doc.label = field["label"]
    doc.fieldtype = field["fieldtype"]
    doc.options = field.get("options")
    doc.insert_after = field.get("insert_after")
    doc.allow_on_submit = 1
    doc.read_only = 1
    doc.no_copy = 1
    doc.insert(ignore_permissions=True)


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
    if "Real Remittance Payment Entry Source Harness" not in text_blob:
        content.append(
            {
                "id": "ndis_real_remittance_pe_source_harness_heading",
                "type": "header",
                "data": {"text": "Real Remittance Payment Entry Source Harness", "col": 12},
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
        "doctypes": {dt: bool(frappe.db.exists("DocType", dt)) for dt in PHASE6E_DOCTYPES},
        "custom_fields": check_custom_fields(),
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
            for dt in PHASE6E_DOCTYPES
        },
        "service_import": can_import_service(),
        "workspace_shortcuts": check_workspace_shortcuts(),
        "action_permissions": {
            "run_real_remittance_pe_source_harness": permission_matrix().get("run_real_remittance_pe_source_harness"),
            "cancel_real_remittance_pe_source_harness_audit": permission_matrix().get("cancel_real_remittance_pe_source_harness_audit"),
        },
        "js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_js,
        },
        "list_js_hooks": {
            RUN_DOCTYPE: RUN_DOCTYPE in doctype_list_js,
            LINE_DOCTYPE: LINE_DOCTYPE in doctype_list_js,
        },
        "sandbox_config_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode_detected": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_payment_entry_posting_config": int(
            frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0
        ),
    }


def check_custom_fields():
    result = {}
    for dt, field_list in CUSTOM_FIELDS.items():
        for field in field_list:
            key = f"{dt}.{field['fieldname']}"
            result[key] = bool(
                frappe.db.exists("Custom Field", {"dt": dt, "fieldname": field["fieldname"]})
            )
    return result


def can_import_service():
    try:
        from ndis_finance.services.real_remittance_pe_source_harness import quick_real_remittance_pe_source_harness_summary

        return callable(quick_real_remittance_pe_source_harness_summary)
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
