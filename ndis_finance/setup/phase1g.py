import frappe
from frappe import _

from ndis_finance.setup.install import MODULE


REPORTS = [
    {
        "report_name": "NDIS CFO Exception Dashboard",
        "ref_doctype": "NDIS Recovery Case",
    },
    {
        "report_name": "NDIS Recovery Ageing Report",
        "ref_doctype": "NDIS Recovery Case",
    },
    {
        "report_name": "NDIS Claim Exception Report",
        "ref_doctype": "NDIS Claim Line",
    },
    {
        "report_name": "NDIS Funding Leakage Report",
        "ref_doctype": "NDIS Funding Leakage Register",
    },
]

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Recovery Officer",
]


@frappe.whitelist()
def install():
    validate_phase1f()
    create_reports()
    frappe.db.commit()
    return health_check()


def validate_phase1f():
    required_doctypes = [
        "NDIS Recovery Case",
        "NDIS Recovery Activity",
        "NDIS Claim Line",
        "NDIS Funding Leakage Register",
        "NDIS Payment Reconciliation Batch",
        "NDIS Payment Reconciliation Line",
        "Report",
    ]

    missing = [dt for dt in required_doctypes if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1G requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )

    missing_roles = [role for role in REPORT_ROLES if not frappe.db.exists("Role", role)]
    if missing_roles:
        frappe.throw(
            _("Missing roles required for Phase 1G reports: {0}").format(
                ", ".join(missing_roles)
            )
        )


def create_reports():
    for report in REPORTS:
        ensure_script_report(
            report_name=report["report_name"],
            ref_doctype=report["ref_doctype"],
        )


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


@frappe.whitelist()
def health_check():
    report_status = {
        report["report_name"]: bool(frappe.db.exists("Report", report["report_name"]))
        for report in REPORTS
    }

    report_details = {}
    for report in REPORTS:
        if frappe.db.exists("Report", report["report_name"]):
            doc = frappe.get_doc("Report", report["report_name"])
            report_details[report["report_name"]] = {
                "report_type": doc.report_type,
                "module": doc.module,
                "is_standard": doc.is_standard,
                "ref_doctype": doc.ref_doctype,
                "roles": [row.role for row in doc.roles],
            }

    return {
        "reports": report_status,
        "report_details": report_details,
    }
