import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from ndis_finance.setup.install import MODULE


PLAN_BUDGET_FIELDS = [
    "service_type",
    "support_item",
    "budget_control_level",
    "budget_control_mode",
    "warning_threshold_percent",
    "last_recalculated_on",
    "validation_notes",
]

SERVICE_BOOKING_FIELDS = [
    "service_type",
    "support_category",
    "booking_control_mode",
    "last_recalculated_on",
    "validation_notes",
]

SALES_INVOICE_FIELDS = [
    "custom_ndis_budget_control_mode",
    "custom_ndis_service_booking_control_mode",
    "custom_ndis_validation_status",
    "custom_ndis_validation_last_run",
]

SALES_INVOICE_ITEM_FIELDS = [
    "custom_ndis_plan_budget",
    "custom_ndis_service_booking",
    "custom_ndis_budget_check_status",
    "custom_ndis_service_booking_check_status",
    "custom_ndis_budget_remaining_before",
    "custom_ndis_budget_remaining_after",
    "custom_ndis_booking_remaining_before",
    "custom_ndis_booking_remaining_after",
    "custom_ndis_budget_validation_note",
]


@frappe.whitelist()
def install():
    validate_phase1b()
    create_phase1c_custom_fields()
    frappe.db.commit()
    return health_check()


def validate_phase1b():
    required_doctypes = [
        "NDIS Plan Budget",
        "NDIS Service Booking",
        "NDIS Support Item",
        "NDIS Service Type",
        "NDIS Funding Source",
        "Sales Invoice",
        "Sales Invoice Item",
        "Customer",
    ]

    missing = [dt for dt in required_doctypes if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1C requires Phase 1A/1B. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )

    required_custom_fields = [
        ("Sales Invoice", "custom_is_ndis_invoice"),
        ("Sales Invoice", "custom_ndis_funding_source"),
        ("Sales Invoice Item", "custom_ndis_support_item"),
        ("Sales Invoice Item", "custom_ndis_service_type"),
        ("Sales Invoice Item", "custom_ndis_service_date"),
        ("Sales Invoice Item", "custom_ndis_claimable"),
    ]

    missing_fields = []
    for dt, fieldname in required_custom_fields:
        if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
            missing_fields.append(f"{dt}.{fieldname}")

    if missing_fields:
        frappe.throw(
            _("Phase 1C requires missing Phase 1A/1B fields: {0}").format(
                ", ".join(missing_fields)
            )
        )


def create_phase1c_custom_fields():
    custom_fields = {
        "NDIS Plan Budget": [
            {
                "fieldname": "service_type",
                "label": "Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "insert_after": "support_category",
                "module": MODULE,
            },
            {
                "fieldname": "support_item",
                "label": "Support Item",
                "fieldtype": "Link",
                "options": "NDIS Support Item",
                "insert_after": "service_type",
                "module": MODULE,
            },
            {
                "fieldname": "budget_control_level",
                "label": "Budget Control Level",
                "fieldtype": "Select",
                "options": "\nParticipant Total\nSupport Category\nService Type\nSupport Item",
                "default": "Service Type",
                "insert_after": "support_item",
                "module": MODULE,
            },
            {
                "fieldname": "budget_control_mode",
                "label": "Budget Control Mode",
                "fieldtype": "Select",
                "options": "\nWarn and Block\nWarn Only\nDisabled",
                "default": "Warn Only",
                "insert_after": "status",
                "module": MODULE,
            },
            {
                "fieldname": "warning_threshold_percent",
                "label": "Warning Threshold %",
                "fieldtype": "Percent",
                "default": "80",
                "insert_after": "budget_control_mode",
                "module": MODULE,
            },
            {
                "fieldname": "last_recalculated_on",
                "label": "Last Recalculated On",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "warning_threshold_percent",
                "module": MODULE,
            },
            {
                "fieldname": "validation_notes",
                "label": "Validation Notes",
                "fieldtype": "Small Text",
                "insert_after": "last_recalculated_on",
                "module": MODULE,
            },
        ],
        "NDIS Service Booking": [
            {
                "fieldname": "service_type",
                "label": "Service Type",
                "fieldtype": "Link",
                "options": "NDIS Service Type",
                "insert_after": "support_item",
                "module": MODULE,
            },
            {
                "fieldname": "support_category",
                "label": "Support Category",
                "fieldtype": "Data",
                "insert_after": "service_type",
                "module": MODULE,
            },
            {
                "fieldname": "booking_control_mode",
                "label": "Booking Control Mode",
                "fieldtype": "Select",
                "options": "\nWarn and Block\nWarn Only\nDisabled",
                "default": "Warn Only",
                "insert_after": "status",
                "module": MODULE,
            },
            {
                "fieldname": "last_recalculated_on",
                "label": "Last Recalculated On",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "booking_control_mode",
                "module": MODULE,
            },
            {
                "fieldname": "validation_notes",
                "label": "Validation Notes",
                "fieldtype": "Small Text",
                "insert_after": "last_recalculated_on",
                "module": MODULE,
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "custom_ndis_budget_control_mode",
                "label": "NDIS Budget Control Mode",
                "fieldtype": "Select",
                "options": "\nWarn and Block\nWarn Only\nDisabled",
                "default": "Warn Only",
                "insert_after": "custom_ndis_price_control_mode",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_booking_control_mode",
                "label": "NDIS Service Booking Control Mode",
                "fieldtype": "Select",
                "options": "\nWarn and Block\nWarn Only\nDisabled",
                "default": "Warn Only",
                "insert_after": "custom_ndis_budget_control_mode",
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_validation_status",
                "label": "NDIS Validation Status",
                "fieldtype": "Select",
                "options": "\nNot Checked\nPassed\nPassed With Warnings\nBlocked",
                "default": "Not Checked",
                "insert_after": "custom_ndis_service_booking_control_mode",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_validation_last_run",
                "label": "NDIS Validation Last Run",
                "fieldtype": "Datetime",
                "insert_after": "custom_ndis_validation_status",
                "read_only": 1,
                "depends_on": "eval:doc.custom_is_ndis_invoice",
                "module": MODULE,
            },
        ],
        "Sales Invoice Item": [
            {
                "fieldname": "custom_ndis_plan_budget",
                "label": "NDIS Plan Budget",
                "fieldtype": "Link",
                "options": "NDIS Plan Budget",
                "insert_after": "custom_ndis_catalogue_version",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_booking",
                "label": "NDIS Service Booking",
                "fieldtype": "Link",
                "options": "NDIS Service Booking",
                "insert_after": "custom_ndis_plan_budget",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_budget_check_status",
                "label": "Budget Check Status",
                "fieldtype": "Select",
                "options": "\nNot Checked\nWithin Budget\nOver Budget\nNo Budget Found\nPlan Expired\nDisabled\nWarning Only",
                "default": "Not Checked",
                "insert_after": "custom_ndis_service_booking",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_service_booking_check_status",
                "label": "Service Booking Check Status",
                "fieldtype": "Select",
                "options": "\nNot Checked\nWithin Booking\nOver Booking\nNo Booking Found\nBooking Expired\nDisabled\nWarning Only",
                "default": "Not Checked",
                "insert_after": "custom_ndis_budget_check_status",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_budget_remaining_before",
                "label": "Budget Remaining Before",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_service_booking_check_status",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_budget_remaining_after",
                "label": "Budget Remaining After",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_budget_remaining_before",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_booking_remaining_before",
                "label": "Booking Remaining Before",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_budget_remaining_after",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_booking_remaining_after",
                "label": "Booking Remaining After",
                "fieldtype": "Currency",
                "insert_after": "custom_ndis_booking_remaining_before",
                "read_only": 1,
                "module": MODULE,
            },
            {
                "fieldname": "custom_ndis_budget_validation_note",
                "label": "Budget / Booking Validation Note",
                "fieldtype": "Small Text",
                "insert_after": "custom_ndis_booking_remaining_after",
                "read_only": 1,
                "module": MODULE,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)


@frappe.whitelist()
def health_check():
    plan_budget_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Plan Budget", "fieldname": fieldname},
            )
        )
        for fieldname in PLAN_BUDGET_FIELDS
    }

    service_booking_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "NDIS Service Booking", "fieldname": fieldname},
            )
        )
        for fieldname in SERVICE_BOOKING_FIELDS
    }

    sales_invoice_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice", "fieldname": fieldname},
            )
        )
        for fieldname in SALES_INVOICE_FIELDS
    }

    sales_invoice_item_fields = {
        fieldname: bool(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Sales Invoice Item", "fieldname": fieldname},
            )
        )
        for fieldname in SALES_INVOICE_ITEM_FIELDS
    }

    return {
        "plan_budget_fields": plan_budget_fields,
        "service_booking_fields": service_booking_fields,
        "sales_invoice_fields": sales_invoice_fields,
        "sales_invoice_item_fields": sales_invoice_item_fields,
    }
