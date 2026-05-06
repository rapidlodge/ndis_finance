app_name = "ndis_finance"
app_title = "NDIS Finance"
app_publisher = "Rapid Lodgements"
app_description = "Australian NDIS finance control layer for ERPNext Accounting"
app_email = "info@rapidlodge.com.au"
app_license = "MIT"

# Run safe setup after install / migrate.
after_install = "ndis_finance.setup.install.after_install"
after_migrate = "ndis_finance.setup.install.after_migrate"

# Safe extension points. No ERPNext core override.
doc_events = {
    "Sales Invoice": {
        "validate": "ndis_finance.overrides.sales_invoice.validate_sales_invoice",
        "on_submit": "ndis_finance.services.budget_control.update_usage_from_sales_invoice",
        "on_cancel": "ndis_finance.services.budget_control.update_usage_from_sales_invoice",
    }
}

# Fixture strategy:
# Keep roles, custom fields and accounting dimensions portable.
fixtures = [
    {
        "dt": "Role",
        "filters": [
            [
                "name",
                "in",
                [
                    "NDIS Finance Manager",
                    "NDIS Finance Officer",
                    "NDIS Finance Read Only",
                    "NDIS Billing Officer",
                    "NDIS Claims Officer",
                    "NDIS Recovery Officer",
                    "NDIS CFO",
                ],
            ]
        ],
    },
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "NDIS Finance"]],
    },
    {
        "dt": "Accounting Dimension",
        "filters": [
            [
                "fieldname",
                "in",
                [
                    "ndis_participant",
                    "ndis_house",
                    "ndis_support_item",
                    "ndis_service_type",
                    "ndis_funding_source",
                    "ndis_claim_batch",
                ],
            ]
        ],
    },
    {
        "dt": "DocType",
        "filters": [
            [
                "name",
                "in",
                [
                    "NDIS House",
                    "NDIS Support Item",
                    "NDIS Service Type",
                    "NDIS Funding Source",
                    "NDIS Participant Financial Profile",
                    "NDIS Plan Budget",
                    "NDIS Service Booking",
                    "NDIS Claim Batch",
                    "NDIS Funding Leakage Register",
                    "NDIS Catalogue Import",
                ],
            ]
        ],
    },
]
