import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


MODULE = "NDIS Finance"
SETUP_PHASES = (
    "ndis_finance.setup.phase1b.install",
    "ndis_finance.setup.phase1c.install",
    "ndis_finance.setup.phase1d.install",
    "ndis_finance.setup.phase1e.install",
    "ndis_finance.setup.phase1f.install",
    "ndis_finance.setup.phase1g.install",
    "ndis_finance.setup.phase1h.install",
    "ndis_finance.setup.phase1j.install",
    "ndis_finance.setup.phase1k.install",
    "ndis_finance.setup.phase1l.install",
    "ndis_finance.setup.phase1m.install",
    "ndis_finance.setup.phase1n.install",
    "ndis_finance.setup.phase1o.install",
    "ndis_finance.setup.phase1p.install",
    "ndis_finance.setup.phase1q.install",
    "ndis_finance.setup.phase1r.install",
    "ndis_finance.setup.phase1s.install",
    "ndis_finance.setup.phase1t.install",
    "ndis_finance.setup.phase1u.install",
    "ndis_finance.setup.phase1v.install",
    "ndis_finance.setup.phase1w.install",
    "ndis_finance.setup.phase1x.install",
    "ndis_finance.setup.phase1y.install",
    "ndis_finance.setup.phase1z.install",
    "ndis_finance.setup.phase2a.install",
    "ndis_finance.setup.phase2b.install",
    "ndis_finance.setup.phase2c.install",
    "ndis_finance.setup.phase2d.install",
    "ndis_finance.setup.phase2e.install",
    "ndis_finance.setup.phase2f.install",
    "ndis_finance.setup.phase3a.install",
    "ndis_finance.setup.phase3b.install",
    "ndis_finance.setup.phase3c.install",
    "ndis_finance.setup.phase3d.install",
    "ndis_finance.setup.phase3e.install",
    "ndis_finance.setup.phase4a.install",
    "ndis_finance.setup.phase4b.install",
    "ndis_finance.setup.phase4c.install",
    "ndis_finance.setup.phase4d.install",
    "ndis_finance.setup.phase5a.install",
    "ndis_finance.setup.phase5b.install",
    "ndis_finance.setup.phase5c.install",
    "ndis_finance.setup.phase5d.install",
    "ndis_finance.setup.phase5e.install",
    "ndis_finance.setup.phase5f.install",
    "ndis_finance.setup.phase5g.install",
    "ndis_finance.setup.phase5h.install",
    "ndis_finance.setup.phase5i.install",
    "ndis_finance.setup.phase5j.install",
    "ndis_finance.setup.phase5k.install",
    "ndis_finance.setup.phase6a.install",
    "ndis_finance.setup.phase6b.install",
    "ndis_finance.setup.phase6c.install",
    "ndis_finance.setup.phase6d.install",
    "ndis_finance.setup.phase6e.install",
    "ndis_finance.setup.phase6f.install",
    "ndis_finance.setup.phase6g.install",
    "ndis_finance.setup.phase6h.install",
    "ndis_finance.setup.phase7a.install",
    "ndis_finance.setup.phase7b.install",
    "ndis_finance.setup.phase7c.install",
    "ndis_finance.setup.phase7d.install",
    "ndis_finance.setup.phase7e.install",
    "ndis_finance.setup.phase7f.install",
    "ndis_finance.setup.phase7g.install",
    "ndis_finance.setup.phase7h.install",
    "ndis_finance.setup.phase8a.install",
    "ndis_finance.setup.phase8b.install",
    "ndis_finance.setup.phase8c.install",
    "ndis_finance.setup.phase8d.install",
    "ndis_finance.setup.phase8e.install",
    "ndis_finance.setup.phase8f.install",
    "ndis_finance.setup.phase8g.install",
    "ndis_finance.setup.phase9a.install",
    "ndis_finance.setup.phase9b.install",
    "ndis_finance.setup.phase9c.install",
    "ndis_finance.setup.phase9d.install",
    "ndis_finance.setup.phase9e.install",
    "ndis_finance.setup.phase9f.install",
    "ndis_finance.setup.phase9g.install",
    "ndis_finance.setup.phase9h.install",
    "ndis_finance.setup.phase9i.install",
    "ndis_finance.setup.phase9j.install",
    "ndis_finance.setup.phase9k.install",
    "ndis_finance.setup.phase9l.install",
    "ndis_finance.setup.phase9m.install",
    "ndis_finance.setup.phase9n.install",
    "ndis_finance.setup.phase9o.install",
    "ndis_finance.setup.phase9p.install",
    "ndis_finance.setup.phase9q.install",
    "ndis_finance.setup.phase9r.install",
    "ndis_finance.setup.phase9s.install",
    "ndis_finance.setup.phase9t.install",
    "ndis_finance.setup.phase9u.install",
    "ndis_finance.setup.phase9v.install",
    "ndis_finance.setup.phase9w.install",
    "ndis_finance.setup.phase9x.install",
    "ndis_finance.setup.phase9y.install",
    "ndis_finance.setup.phase9z.install",
    "ndis_finance.setup.phase10a.install",
    "ndis_finance.setup.phase10b.install",
    "ndis_finance.setup.phase10c.install",
    "ndis_finance.setup.phase10d.install",
    "ndis_finance.setup.phase10e.install",
    "ndis_finance.setup.phase10f.install",
    "ndis_finance.setup.phase10g.install",
    "ndis_finance.setup.phase10h.install",
    "ndis_finance.setup.phase10i.install",
    "ndis_finance.setup.phase10j.install",
    "ndis_finance.setup.phase10k.install",
    "ndis_finance.setup.phase10l.install",
    "ndis_finance.setup.phase10m.install",
    "ndis_finance.setup.phase10n.install",
    "ndis_finance.setup.phase10o.install",
    "ndis_finance.setup.phase10p.install",
    "ndis_finance.setup.phase10q.install",
    "ndis_finance.setup.phase10r.install",
    "ndis_finance.setup.phase10s.install",
    "ndis_finance.setup.phase10t.install",
    "ndis_finance.setup.phase10u.install",
    "ndis_finance.setup.phase10v.install",
    "ndis_finance.setup.phase10w.install",
    "ndis_finance.setup.phase10x.install",
    "ndis_finance.setup.phase10y.install",
    "ndis_finance.setup.phase10z.install",
    "ndis_finance.setup.phase11a.install",
    "ndis_finance.setup.phase11b.install",
    "ndis_finance.setup.phase11c.install",
    "ndis_finance.setup.phase11d.install",
    "ndis_finance.setup.phase11e.install",
    "ndis_finance.setup.phase11f.install",
    "ndis_finance.setup.phase11g.install",
    "ndis_finance.setup.phase11h.install",
    "ndis_finance.setup.phase11i.install",
    "ndis_finance.setup.phase11j.install",
    "ndis_finance.setup.phase11k.install",
    "ndis_finance.setup.phase11l.install",
    "ndis_finance.setup.phase11m.install",
    "ndis_finance.setup.phase11n.install",
    "ndis_finance.setup.phase11o.install",
    "ndis_finance.setup.phase11p.install",
    "ndis_finance.setup.phase11q.install",
    "ndis_finance.setup.phase11r.install",
    "ndis_finance.setup.phase11s.install",
    "ndis_finance.setup.phase11t.install",
    "ndis_finance.setup.phase11u.install",
    "ndis_finance.setup.phase11v.install",
    "ndis_finance.setup.phase11w.install",
    "ndis_finance.setup.phase11x.install",
    "ndis_finance.setup.phase11y.install",
    "ndis_finance.setup.phase11z.install",
    "ndis_finance.setup.phase12a.install",
    "ndis_finance.setup.phase12b.install",
    "ndis_finance.setup.phase12c.install",
    "ndis_finance.setup.phase12d.install",
    "ndis_finance.setup.phase12e.install",
    "ndis_finance.setup.phase12f.install",
    "ndis_finance.setup.phase12g.install",
    "ndis_finance.setup.phase12h.install",
    "ndis_finance.setup.phase12i.install",
    "ndis_finance.setup.phase12j.install",
    "ndis_finance.setup.phase12k.install",
    "ndis_finance.setup.phase12l.install",
    "ndis_finance.setup.phase12m.install",
    "ndis_finance.setup.phase12n.install",
    "ndis_finance.setup.phase12o.install",
    "ndis_finance.setup.phase12p.install",
    "ndis_finance.setup.phase12q.install",
    "ndis_finance.setup.phase12r.install",
    "ndis_finance.setup.phase12s.install",
    "ndis_finance.setup.phase12t.install",
    "ndis_finance.setup.phase12u.install",
    "ndis_finance.setup.phase12v.install",
    "ndis_finance.setup.phase12w.install",
    "ndis_finance.setup.phase12x.install",
    "ndis_finance.setup.phase12y.install",
    "ndis_finance.setup.phase12z.install",
)

ROLES = [
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Finance Read Only",
    "NDIS Billing Officer",
    "NDIS Claims Officer",
    "NDIS Recovery Officer",
    "NDIS CFO",
]

CUSTOM_DOCTYPES = [
    "NDIS House",
    "NDIS Support Item",
    "NDIS Service Type",
    "NDIS Funding Source",
    "NDIS Participant Financial Profile",
    "NDIS Plan Budget",
    "NDIS Service Booking",
    "NDIS Claim Batch",
    "NDIS Funding Leakage Register",
]

ACCOUNTING_DIMENSIONS = [
    {
        "label": "NDIS Participant",
        "fieldname": "ndis_participant",
        "document_type": "Customer",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
    {
        "label": "NDIS House",
        "fieldname": "ndis_house",
        "document_type": "NDIS House",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
    {
        "label": "NDIS Support Item",
        "fieldname": "ndis_support_item",
        "document_type": "NDIS Support Item",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
    {
        "label": "NDIS Service Type",
        "fieldname": "ndis_service_type",
        "document_type": "NDIS Service Type",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
    {
        "label": "NDIS Funding Source",
        "fieldname": "ndis_funding_source",
        "document_type": "NDIS Funding Source",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
    {
        "label": "NDIS Claim Batch",
        "fieldname": "ndis_claim_batch",
        "document_type": "NDIS Claim Batch",
        "mandatory_for_pl": 0,
        "mandatory_for_bs": 0,
    },
]


def before_install():
    validate_required_apps_and_doctypes()


def after_install():
    install()


def after_migrate():
    install()


@frappe.whitelist()
def install():
    """
    Idempotent installer.
    Safe to run many times.
    """
    validate_required_apps_and_doctypes()
    ensure_module_def()
    create_roles()
    create_custom_doctypes()
    create_seed_records()
    create_ndis_custom_fields()
    create_accounting_dimensions()
    frappe.db.commit()
    run_setup_phases()
    return health_check()


def run_setup_phases():
    for phase in SETUP_PHASES:
        frappe.get_attr(phase)()


def validate_required_apps_and_doctypes():
    required_doctypes = [
        "Company",
        "Customer",
        "Sales Invoice",
        "Sales Invoice Item",
        "Payment Entry",
        "Journal Entry",
        "Accounting Dimension",
        "Custom Field",
        "Role",
    ]

    missing = [dt for dt in required_doctypes if not frappe.db.exists("DocType", dt)]
    if missing:
        frappe.throw(
            _("NDIS Finance requires ERPNext Accounting. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )


def ensure_module_def():
    if not frappe.db.exists("Module Def", MODULE):
        frappe.get_doc(
            {
                "doctype": "Module Def",
                "module_name": MODULE,
                "app_name": "ndis_finance",
                "custom": 0,
            }
        ).insert(ignore_permissions=True)


def create_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)


def _default_permissions():
    return [
        {
            "role": "System Manager",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "export": 1,
            "print": 1,
            "email": 1,
            "report": 1,
        },
        {
            "role": "NDIS Finance Manager",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "export": 1,
            "print": 1,
            "email": 1,
            "report": 1,
        },
        {
            "role": "NDIS Finance Officer",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "export": 1,
            "print": 1,
            "email": 1,
            "report": 1,
        },
        {
            "role": "NDIS Finance Read Only",
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "export": 1,
            "print": 1,
            "email": 0,
            "report": 1,
        },
    ]


def _create_doctype(name, autoname, title_field, fields, is_submittable=0):
    if frappe.db.exists("DocType", name):
        return

    doc = frappe.get_doc(
        {
            "doctype": "DocType",
            "name": name,
            "module": MODULE,
            "custom": 1,
            "istable": 0,
            "is_submittable": is_submittable,
            "editable_grid": 1,
            "track_changes": 1,
            "autoname": autoname,
            "title_field": title_field,
            "fields": fields,
            "permissions": _default_permissions(),
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.clear_cache(doctype=name)


def create_custom_doctypes():
    create_ndis_house_doctype()
    create_ndis_funding_source_doctype()
    create_ndis_service_type_doctype()
    create_ndis_support_item_doctype()
    create_participant_financial_profile_doctype()
    create_plan_budget_doctype()
    create_service_booking_doctype()
    create_claim_batch_doctype()
    create_funding_leakage_register_doctype()


def create_ndis_house_doctype():
    _create_doctype(
        name="NDIS House",
        autoname="field:house_name",
        title_field="house_name",
        fields=[
            {
                "fieldname": "house_name",
                "label": "House Name",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "region",
                "label": "Region",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "house_type",
                "label": "House Type",
                "fieldtype": "Select",
                "options": "\nSIL\nSDA\nSIL + SDA\nCommunity\nOther",
                "in_list_view": 1,
            },
            {
                "fieldname": "cost_center",
                "label": "Default Cost Center",
                "fieldtype": "Link",
                "options": "Cost Center",
            },
            {
                "fieldname": "company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
            },
            {
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
            },
        ],
    )


def create_ndis_funding_source_doctype():
    _create_doctype(
        name="NDIS Funding Source",
        autoname="field:funding_source_name",
        title_field="funding_source_name",
        fields=[
            {
                "fieldname": "funding_source_name",
                "label": "Funding Source Name",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
            },
        ],
    )


def create_ndis_service_type_doctype():
    _create_doctype(
        name="NDIS Service Type",
        autoname="field:service_type_name",
        title_field="service_type_name",
        fields=[
            {
                "fieldname": "service_type_name",
                "label": "Service Type Name",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "service_group",
                "label": "Service Group",
                "fieldtype": "Select",
                "options": "\nSIL\nSDA\nCore\nCapacity Building\nSupport Coordination\nTransport\nOther",
                "in_list_view": 1,
            },
            {
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
            },
        ],
    )


def create_ndis_support_item_doctype():
    _create_doctype(
        name="NDIS Support Item",
        autoname="field:support_item_number",
        title_field="support_item_name",
        fields=[
            {
                "fieldname": "support_item_number",
                "label": "Support Item Number",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "support_item_name",
                "label": "Support Item Name",
                "fieldtype": "Data",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "support_category",
                "label": "Support Category",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "registration_group",
                "label": "Registration Group",
                "fieldtype": "Data",
            },
            {
                "fieldname": "service_type",
                "label": "Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "in_list_view": 1,
            },
            {
                "fieldname": "unit",
                "label": "Unit",
                "fieldtype": "Data",
            },
            {
                "fieldname": "price_limit",
                "label": "Price Limit",
                "fieldtype": "Currency",
                "in_list_view": 1,
            },
            {
                "fieldname": "gst_treatment",
                "label": "GST Treatment",
                "fieldtype": "Select",
                "options": "\nGST Free\nTaxable\nInput Taxed\nOut of Scope\nTo Review",
                "default": "To Review",
                "in_list_view": 1,
            },
            {
                "fieldname": "catalogue_version",
                "label": "Catalogue Version",
                "fieldtype": "Data",
            },
            {
                "fieldname": "effective_from",
                "label": "Effective From",
                "fieldtype": "Date",
            },
            {
                "fieldname": "effective_to",
                "label": "Effective To",
                "fieldtype": "Date",
            },
            {
                "fieldname": "is_sil",
                "label": "SIL",
                "fieldtype": "Check",
            },
            {
                "fieldname": "is_sda",
                "label": "SDA",
                "fieldtype": "Check",
            },
            {
                "fieldname": "is_group_support",
                "label": "Group Support",
                "fieldtype": "Check",
            },
            {
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
            },
        ],
    )


def create_participant_financial_profile_doctype():
    _create_doctype(
        name="NDIS Participant Financial Profile",
        autoname="field:profile_name",
        title_field="profile_name",
        fields=[
            {
                "fieldname": "profile_name",
                "label": "Profile Name",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "participant",
                "label": "Participant / Customer",
                "fieldtype": "Link",
                "options": "Customer",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "ndis_number",
                "label": "NDIS Number",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "in_list_view": 1,
            },
            {
                "fieldname": "plan_start_date",
                "label": "Plan Start Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "plan_end_date",
                "label": "Plan End Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "default_house",
                "label": "Default House",
                "fieldtype": "Link",
                "options": "NDIS House",
            },
            {
                "fieldname": "default_cost_center",
                "label": "Default Cost Center",
                "fieldtype": "Link",
                "options": "Cost Center",
            },
            {
                "fieldname": "billing_hold",
                "label": "Billing Hold",
                "fieldtype": "Check",
            },
            {
                "fieldname": "billing_hold_reason",
                "label": "Billing Hold Reason",
                "fieldtype": "Small Text",
                "depends_on": "eval:doc.billing_hold",
            },
            {
                "fieldname": "active",
                "label": "Active",
                "fieldtype": "Check",
                "default": "1",
            },
        ],
    )


def create_plan_budget_doctype():
    _create_doctype(
        name="NDIS Plan Budget",
        autoname="field:budget_name",
        title_field="budget_name",
        fields=[
            {
                "fieldname": "budget_name",
                "label": "Budget Name",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "support_category",
                "label": "Support Category",
                "fieldtype": "Data",
                "in_list_view": 1,
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
            },
            {
                "fieldname": "plan_start_date",
                "label": "Plan Start Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "plan_end_date",
                "label": "Plan End Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "budget_amount",
                "label": "Budget Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "claimed_amount",
                "label": "Claimed Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "paid_amount",
                "label": "Paid Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "remaining_budget",
                "label": "Remaining Budget",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nActive\nExhausted\nExpired\nClosed",
                "default": "Draft",
                "in_list_view": 1,
            },
        ],
    )


def create_service_booking_doctype():
    _create_doctype(
        name="NDIS Service Booking",
        autoname="field:booking_reference",
        title_field="booking_reference",
        fields=[
            {
                "fieldname": "booking_reference",
                "label": "Booking Reference",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "support_item",
                "label": "Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
                "in_list_view": 1,
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
            },
            {
                "fieldname": "start_date",
                "label": "Start Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "end_date",
                "label": "End Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "booking_amount",
                "label": "Booking Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "used_amount",
                "label": "Used Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "remaining_amount",
                "label": "Remaining Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nActive\nExpired\nExhausted\nClosed",
                "default": "Active",
                "in_list_view": 1,
            },
        ],
    )


def create_claim_batch_doctype():
    _create_doctype(
        name="NDIS Claim Batch",
        autoname="field:claim_batch_id",
        title_field="claim_batch_id",
        is_submittable=0,
        fields=[
            {
                "fieldname": "claim_batch_id",
                "label": "Claim Batch ID",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_period_start",
                "label": "Claim Period Start",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "claim_period_end",
                "label": "Claim Period End",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nDraft\nSubmitted\nPart Paid\nPaid\nRejected\nClosed",
                "default": "Draft",
                "in_list_view": 1,
            },
            {
                "fieldname": "total_claim_amount",
                "label": "Total Claim Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "total_paid_amount",
                "label": "Total Paid Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
            {
                "fieldname": "total_shortfall_amount",
                "label": "Total Shortfall Amount",
                "fieldtype": "Currency",
                "read_only": 1,
            },
        ],
    )


def create_funding_leakage_register_doctype():
    _create_doctype(
        name="NDIS Funding Leakage Register",
        autoname="hash",
        title_field="leakage_type",
        fields=[
            {
                "fieldname": "participant",
                "label": "Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "in_list_view": 1,
            },
            {
                "fieldname": "house",
                "label": "House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "in_list_view": 1,
            },
            {
                "fieldname": "service_date",
                "label": "Service Date",
                "fieldtype": "Date",
                "in_list_view": 1,
            },
            {
                "fieldname": "leakage_type",
                "label": "Leakage Type",
                "fieldtype": "Select",
                "options": "\nUnclaimed Shift\nUnderbilling\nOverbilling Risk\nMissing Support Item\nMissing Service Booking\nPlan Expired\nBudget Exhausted\nPayment Shortfall\nRejected Claim\nOther",
                "in_list_view": 1,
            },
            {
                "fieldname": "source_doctype",
                "label": "Source DocType",
                "fieldtype": "Link",
                "options": "DocType",
            },
            {
                "fieldname": "source_name",
                "label": "Source Name",
                "fieldtype": "Dynamic Link",
                "options": "source_doctype",
            },
            {
                "fieldname": "expected_amount",
                "label": "Expected Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "actual_amount",
                "label": "Actual Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "variance_amount",
                "label": "Variance Amount",
                "fieldtype": "Currency",
            },
            {
                "fieldname": "severity",
                "label": "Severity",
                "fieldtype": "Select",
                "options": "\nLow\nMedium\nHigh\nCritical",
                "default": "Medium",
                "in_list_view": 1,
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nOpen\nIn Review\nResolved\nWritten Off\nClosed",
                "default": "Open",
                "in_list_view": 1,
            },
            {
                "fieldname": "resolution_note",
                "label": "Resolution Note",
                "fieldtype": "Small Text",
            },
        ],
    )


def create_seed_records():
    for value in ["NDIA Managed", "Plan Managed", "Self Managed", "Mixed Funding"]:
        if frappe.db.exists("NDIS Funding Source", value):
            continue
        frappe.get_doc(
            {
                "doctype": "NDIS Funding Source",
                "funding_source_name": value,
                "active": 1,
            }
        ).insert(ignore_permissions=True)

    service_types = [
        ("SIL", "SIL"),
        ("SDA", "SDA"),
        ("Core Supports", "Core"),
        ("Community Participation", "Core"),
        ("Support Coordination", "Support Coordination"),
        ("Transport", "Transport"),
        ("Sleepover", "SIL"),
        ("Broken Shift", "SIL"),
        ("Provider Travel", "Transport"),
        ("Other", "Other"),
    ]

    for service_type_name, service_group in service_types:
        if frappe.db.exists("NDIS Service Type", service_type_name):
            continue
        frappe.get_doc(
            {
                "doctype": "NDIS Service Type",
                "service_type_name": service_type_name,
                "service_group": service_group,
                "active": 1,
            }
        ).insert(ignore_permissions=True)


def create_ndis_custom_fields():
    custom_fields = {
        "Customer": [
            {
                "fieldname": "custom_ndis_section",
                "label": "NDIS Finance",
                "fieldtype": "Section Break",
                "insert_after": "tax_id",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_is_ndis_participant",
                "label": "Is NDIS Participant",
                "fieldtype": "Check",
                "insert_after": "custom_ndis_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_number",
                "label": "NDIS Number",
                "fieldtype": "Data",
                "insert_after": "custom_is_ndis_participant",
                "depends_on": "eval:doc.custom_is_ndis_participant",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_funding_source",
                "label": "Default Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "insert_after": "custom_ndis_number",
                "depends_on": "eval:doc.custom_is_ndis_participant",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_default_house",
                "label": "Default NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "insert_after": "custom_ndis_funding_source",
                "depends_on": "eval:doc.custom_is_ndis_participant",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_financial_profile",
                "label": "NDIS Financial Profile",
                "fieldtype": "Link",
                "options": "NDIS Participant Financial Profile",
                "insert_after": "custom_ndis_default_house",
                "depends_on": "eval:doc.custom_is_ndis_participant",
                "module": MODULE,
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "custom_ndis_section",
                "label": "NDIS Billing Control",
                "fieldtype": "Section Break",
                "insert_after": "customer",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_is_ndis_invoice",
                "label": "Is NDIS Invoice",
                "fieldtype": "Check",
                "insert_after": "custom_ndis_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_participant_profile",
                "label": "NDIS Participant Financial Profile",
                "fieldtype": "Link",
                "options": "NDIS Participant Financial Profile",
                "insert_after": "custom_is_ndis_invoice",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "insert_after": "custom_ndis_participant_profile",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_house",
                "label": "NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "insert_after": "custom_ndis_funding_source",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_batch",
                "label": "NDIS Claim Batch",
                "fieldtype": "Link",
                "options": "NDIS Claim Batch",
                "insert_after": "custom_ndis_house",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_billing_status",
                "label": "NDIS Billing Status",
                "fieldtype": "Select",
                "options": "\nDraft\nReady to Claim\nClaimed\nInvoiced to Plan Manager\nPaid\nShort Paid\nRejected\nOn Hold\nWritten Off",
                "default": "Draft",
                "insert_after": "custom_ndis_claim_batch",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_recovery_status",
                "label": "NDIS Recovery Status",
                "fieldtype": "Select",
                "options": "\nNot Due\nFollow Up Required\nIn Recovery\nIn Follow Up\nEscalated\nResolved\nDo Not Recover\nWritten Off",
                "insert_after": "custom_ndis_billing_status",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
        ],
        "Sales Invoice Item": [
            {
                "fieldname": "custom_ndis_line_section",
                "label": "NDIS Line Control",
                "fieldtype": "Section Break",
                "insert_after": "description",
                "collapsible": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_participant",
                "label": "NDIS Participant",
                "fieldtype": "Link",
                "options": "Customer",
                "insert_after": "custom_ndis_line_section",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_house",
                "label": "NDIS House",
                "fieldtype": "Link",
                "options": "NDIS House",
                "insert_after": "custom_ndis_participant",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_support_item",
                "label": "NDIS Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
                "insert_after": "custom_ndis_house",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_type",
                "label": "NDIS Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "insert_after": "custom_ndis_support_item",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_funding_source",
                "label": "Funding Source",
                "fieldtype": "Link",
                "options": "NDIS Funding Source",
                "insert_after": "custom_ndis_service_type",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_date",
                "label": "Service Date",
                "fieldtype": "Date",
                "insert_after": "custom_ndis_funding_source",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claimable",
                "label": "Claimable",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "custom_ndis_service_date",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_claim_status",
                "label": "Claim Status",
                "fieldtype": "Select",
                "options": "\nNot Claimed\nClaimed\nPaid\nShort Paid\nRejected\nNot Claimable",
                "default": "Not Claimed",
                "insert_after": "custom_ndis_claimable",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_rejection_reason",
                "label": "Rejection / Shortfall Reason",
                "fieldtype": "Small Text",
                "insert_after": "custom_ndis_claim_status",
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


def create_accounting_dimensions():
    if not frappe.db.exists("DocType", "Accounting Dimension"):
        return

    for dim in ACCOUNTING_DIMENSIONS:
        if frappe.db.exists("Accounting Dimension", {"fieldname": dim["fieldname"]}):
            continue

        existing_for_doctype = frappe.db.get_value(
            "Accounting Dimension",
            {"document_type": dim["document_type"]},
            "fieldname",
        )
        if existing_for_doctype:
            continue

        doc = frappe.new_doc("Accounting Dimension")
        meta = frappe.get_meta("Accounting Dimension")

        if meta.has_field("document_type"):
            doc.document_type = dim["document_type"]
        if meta.has_field("label"):
            doc.label = dim["label"]
        if meta.has_field("fieldname"):
            doc.fieldname = dim["fieldname"]
        if meta.has_field("disabled"):
            doc.disabled = 0
        if meta.has_field("mandatory_for_pl"):
            doc.mandatory_for_pl = dim.get("mandatory_for_pl", 0)
        if meta.has_field("mandatory_for_bs"):
            doc.mandatory_for_bs = dim.get("mandatory_for_bs", 0)

        doc.insert(ignore_permissions=True)

    frappe.clear_cache()


@frappe.whitelist()
def health_check():
    installed_apps = frappe.get_installed_apps()

    roles = {role: bool(frappe.db.exists("Role", role)) for role in ROLES}

    doctypes = {dt: bool(frappe.db.exists("DocType", dt)) for dt in CUSTOM_DOCTYPES}

    custom_fields_to_check = {
        "Customer": [
            "custom_is_ndis_participant",
            "custom_ndis_number",
            "custom_ndis_funding_source",
            "custom_ndis_default_house",
            "custom_ndis_financial_profile",
        ],
        "Sales Invoice": [
            "custom_is_ndis_invoice",
            "custom_ndis_participant_profile",
            "custom_ndis_funding_source",
            "custom_ndis_house",
            "custom_ndis_claim_batch",
            "custom_ndis_billing_status",
            "custom_ndis_recovery_status",
        ],
        "Sales Invoice Item": [
            "custom_ndis_participant",
            "custom_ndis_house",
            "custom_ndis_support_item",
            "custom_ndis_service_type",
            "custom_ndis_funding_source",
            "custom_ndis_service_date",
            "custom_ndis_claimable",
            "custom_ndis_claim_status",
        ],
    }

    custom_fields = {}
    for dt, fields in custom_fields_to_check.items():
        custom_fields[dt] = {
            fieldname: bool(
                frappe.db.exists(
                    "Custom Field",
                    {
                        "dt": dt,
                        "fieldname": fieldname,
                    },
                )
            )
            for fieldname in fields
        }

    dimensions = {
        dim["fieldname"]: bool(
            frappe.db.exists(
                "Accounting Dimension",
                {
                    "fieldname": dim["fieldname"],
                },
            )
        )
        for dim in ACCOUNTING_DIMENSIONS
    }

    return {
        "installed_apps": {
            "erpnext": "erpnext" in installed_apps,
            "hrms": "hrms" in installed_apps,
            "au_payroll": "au_payroll" in installed_apps,
            "mint": "mint" in installed_apps,
            "ndis_finance": "ndis_finance" in installed_apps,
        },
        "roles": roles,
        "doctypes": doctypes,
        "custom_fields": custom_fields,
        "accounting_dimensions": dimensions,
    }
