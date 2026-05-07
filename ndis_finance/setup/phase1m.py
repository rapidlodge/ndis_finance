import frappe
from frappe import _

from ndis_finance.services.permissions import ACTION_ROLE_MAP, permission_matrix


NEW_ROLES = [
    "NDIS Catalogue Manager",
    "NDIS Budget Manager",
    "NDIS Automation Manager",
    "NDIS Communication Approver",
    "NDIS Write Off Approver",
]

DOC_PERM_MATRIX = {
    "NDIS Support Item": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Catalogue Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Catalogue Import": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Catalogue Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Plan Budget": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Budget Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Billing Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Service Booking": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Budget Manager": "full_no_delete",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Billing Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Claim Batch": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Claim Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Recovery Officer": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Payment Reconciliation Batch": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Payment Reconciliation Line": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Claims Officer": "create_write_read_report",
        "NDIS Recovery Officer": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Funding Leakage Register": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Recovery Officer": "create_write_read_report",
        "NDIS Claims Officer": "read_report_export",
        "NDIS Finance Officer": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Recovery Case": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Recovery Officer": "create_write_read_report",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Recovery Activity": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Recovery Officer": "create_write_read_report",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Recovery Communication Template": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Communication Approver": "read_report_export",
        "NDIS Recovery Officer": "read_report",
        "NDIS Finance Officer": "read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Recovery Email Draft": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "full_no_delete",
        "NDIS Communication Approver": "create_write_read_report",
        "NDIS Recovery Officer": "create_write_read_report",
        "NDIS Finance Officer": "create_write_read_report",
        "NDIS Finance Read Only": "read_report",
    },
    "NDIS Recovery Automation Log": {
        "System Manager": "full",
        "NDIS CFO": "read_report_export",
        "NDIS Finance Manager": "read_report_export",
        "NDIS Automation Manager": "read_report_export",
        "NDIS Finance Read Only": "read_report",
    },
}

REPORT_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Claims Officer",
    "NDIS Recovery Officer",
    "NDIS Finance Read Only",
]

REPORTS = [
    "NDIS CFO Exception Dashboard",
    "NDIS Recovery Ageing Report",
    "NDIS Claim Exception Report",
    "NDIS Funding Leakage Report",
    "NDIS Automation Health Report",
    "NDIS Automation Exception Report",
]


@frappe.whitelist()
def install():
    validate_previous_phases()
    create_new_roles()
    harden_doctype_permissions()
    harden_report_permissions()
    frappe.db.commit()
    frappe.clear_cache()
    return health_check()


def validate_previous_phases():
    required = list(DOC_PERM_MATRIX.keys()) + ["Report", "Role"]
    missing = [dt for dt in required if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1M requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def create_new_roles():
    for role in NEW_ROLES:
        if frappe.db.exists("Role", role):
            continue

        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role,
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)


def harden_doctype_permissions():
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
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
                "report": 1,
                "export": 1,
                "share": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "full_no_delete":
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "report": 1,
                "export": 1,
                "share": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "create_write_read_report":
        base.update(
            {
                "read": 1,
                "write": 1,
                "create": 1,
                "report": 1,
                "export": 1,
                "print": 1,
                "email": 1,
            }
        )
    elif profile == "read_report_export":
        base.update(
            {
                "read": 1,
                "report": 1,
                "export": 1,
                "print": 1,
            }
        )
    elif profile == "read_report":
        base.update(
            {
                "read": 1,
                "report": 1,
            }
        )
    else:
        frappe.throw(_("Unknown permission profile: {0}").format(profile))

    return base


def harden_report_permissions():
    for report_name in REPORTS:
        if not frappe.db.exists("Report", report_name):
            continue

        report = frappe.get_doc("Report", report_name)
        report.roles = []

        for role in REPORT_ROLES:
            if frappe.db.exists("Role", role):
                report.append("roles", {"role": role})

        report.save(ignore_permissions=True)


@frappe.whitelist()
def health_check():
    new_roles_status = {role: bool(frappe.db.exists("Role", role)) for role in NEW_ROLES}
    doctypes = {}

    for doctype, role_map in DOC_PERM_MATRIX.items():
        if not frappe.db.exists("DocType", doctype):
            doctypes[doctype] = {"exists": False}
            continue

        expected_roles = sorted([role for role in role_map if frappe.db.exists("Role", role)])
        perms = frappe.get_all(
            "DocPerm",
            filters={"parent": doctype, "role": ["in", expected_roles]},
            fields=[
                "role",
                "read",
                "write",
                "create",
                "delete",
                "report",
                "export",
                "import",
            ],
        )

        doctypes[doctype] = {
            "exists": True,
            "configured_roles": sorted([perm.role for perm in perms]),
            "expected_roles": expected_roles,
            "role_count": len(perms),
            "healthy": sorted([perm.role for perm in perms]) == expected_roles,
        }

    reports = {}
    for report_name in REPORTS:
        if not frappe.db.exists("Report", report_name):
            reports[report_name] = {"exists": False, "healthy": False}
            continue

        report = frappe.get_doc("Report", report_name)
        report_roles = sorted([row.role for row in report.roles])
        expected_roles = sorted([role for role in REPORT_ROLES if frappe.db.exists("Role", role)])
        reports[report_name] = {
            "exists": True,
            "roles": report_roles,
            "expected_roles": expected_roles,
            "healthy": report_roles == expected_roles,
        }

    return {
        "new_roles": new_roles_status,
        "doctype_permissions": doctypes,
        "reports": reports,
        "action_permission_matrix": permission_matrix(),
        "configured_actions": sorted(ACTION_ROLE_MAP.keys()),
    }
