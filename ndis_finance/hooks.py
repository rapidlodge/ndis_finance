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
        "before_cancel": "ndis_finance.services.claim_batch_engine.before_sales_invoice_cancel",
        "on_cancel": "ndis_finance.services.claim_batch_engine.on_sales_invoice_cancelled",
    }
}

# Fixture strategy:
# Keep roles, custom fields and accounting dimensions portable.
fixtures = [
    {
        "dt": "NDIS Recovery Communication Template",
        "filters": [
            [
                "template_name",
                "in",
                [
                    "NDIS Plan Manager Follow Up",
                    "NDIS Remittance Request",
                    "NDIS Invoice Resend",
                    "NDIS Rejected Claim Follow Up",
                    "NDIS Short Payment Follow Up",
                    "NDIS Write Off Internal Review",
                ],
            ]
        ],
    },
    {
        "dt": "NDIS Claim Export Mapping Template",
        "filters": [
            [
                "template_name",
                "in",
                [
                    "NDIS Default Claim Export",
                    "NDIS Plan Manager Claim Export",
                    "NDIS Self Managed Claim Export",
                    "NDIS Internal Review Claim Export",
                ],
            ]
        ],
    },
    {
        "dt": "Workspace",
        "filters": [["label", "=", "NDIS Finance"]],
    },
    {
        "dt": "Number Card",
        "filters": [
            [
                "label",
                "in",
                [
                    "Open Recovery Cases",
                    "Overdue Follow Ups",
                    "Open Leakage Records",
                    "Open Leakage Amount",
                    "Claim Exception Amount",
                    "Rejected Claims",
                ],
            ]
        ],
    },
    {
        "dt": "Report",
        "filters": [
            [
                "name",
                "in",
                [
                    "NDIS CFO Exception Dashboard",
                    "NDIS Recovery Ageing Report",
                    "NDIS Claim Exception Report",
                    "NDIS Funding Leakage Report",
                    "NDIS Automation Health Report",
                    "NDIS Automation Exception Report",
                    "NDIS Funding Leakage Analytics Report",
                    "NDIS Claim Cycle Time Report",
                    "NDIS House Profitability Foundation Report",
                    "NDIS Participant Profitability Foundation Report",
                ],
            ]
        ],
    },
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
                    "NDIS Catalogue Manager",
                    "NDIS Budget Manager",
                    "NDIS Automation Manager",
                    "NDIS Communication Approver",
                    "NDIS Write Off Approver",
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
                    "NDIS Claim Line",
                    "NDIS Payment Reconciliation Batch",
                    "NDIS Payment Reconciliation Line",
                    "NDIS Recovery Case",
                    "NDIS Recovery Activity",
                    "NDIS Recovery Communication Template",
                    "NDIS Recovery Email Draft",
                    "NDIS Recovery Automation Log",
                    "NDIS Remittance Import",
                    "NDIS Remittance Import Line",
                    "NDIS Claim Export",
                    "NDIS Claim Export Line",
                    "NDIS Claim Export Mapping Template",
                    "NDIS Cost Pool",
                    "NDIS Cost Allocation Entry",
                ],
            ]
        ],
    },
]

# Phase 1I UI polish hooks.
doctype_js = globals().get("doctype_js", {})
doctype_js.update(
    {
        "NDIS Claim Batch": "public/js/ndis_claim_batch.js",
        "NDIS Claim Line": "public/js/ndis_claim_line.js",
        "NDIS Payment Reconciliation Batch": "public/js/ndis_payment_reconciliation_batch.js",
        "NDIS Funding Leakage Register": "public/js/ndis_funding_leakage_register.js",
        "NDIS Recovery Case": "public/js/ndis_recovery_case.js",
        "NDIS Recovery Email Draft": "public/js/ndis_recovery_email_draft.js",
        "NDIS Recovery Automation Log": "public/js/ndis_recovery_automation_log.js",
        "NDIS Remittance Import": "public/js/ndis_remittance_import.js",
        "NDIS Remittance Import Line": "public/js/ndis_remittance_import_line.js",
        "NDIS Claim Export": "public/js/ndis_claim_export.js",
        "NDIS Claim Export Line": "public/js/ndis_claim_export_line.js",
        "NDIS Claim Export Mapping Template": "public/js/ndis_claim_export_mapping_template.js",
        "NDIS Cost Pool": "public/js/ndis_cost_pool.js",
        "NDIS Cost Allocation Entry": "public/js/ndis_cost_allocation_entry.js",
    }
)

doctype_list_js = globals().get("doctype_list_js", {})
doctype_list_js.update(
    {
        "NDIS Claim Batch": "public/js/ndis_claim_batch_list.js",
        "NDIS Claim Line": "public/js/ndis_claim_line_list.js",
        "NDIS Payment Reconciliation Batch": "public/js/ndis_payment_reconciliation_batch_list.js",
        "NDIS Funding Leakage Register": "public/js/ndis_funding_leakage_register_list.js",
        "NDIS Recovery Case": "public/js/ndis_recovery_case_list.js",
        "NDIS Recovery Email Draft": "public/js/ndis_recovery_email_draft_list.js",
        "NDIS Recovery Automation Log": "public/js/ndis_recovery_automation_log_list.js",
        "NDIS Remittance Import": "public/js/ndis_remittance_import_list.js",
        "NDIS Remittance Import Line": "public/js/ndis_remittance_import_line_list.js",
        "NDIS Claim Export": "public/js/ndis_claim_export_list.js",
        "NDIS Claim Export Line": "public/js/ndis_claim_export_line_list.js",
        "NDIS Claim Export Mapping Template": "public/js/ndis_claim_export_mapping_template_list.js",
        "NDIS Cost Pool": "public/js/ndis_cost_pool_list.js",
        "NDIS Cost Allocation Entry": "public/js/ndis_cost_allocation_entry_list.js",
    }
)

# Phase 1K recovery automation scheduler.
scheduler_events = globals().get("scheduler_events", {})
daily_events = scheduler_events.get("daily", [])
if not isinstance(daily_events, list):
    daily_events = list(daily_events)

phase1k_daily_job = "ndis_finance.services.recovery_scheduler.daily_recovery_monitor_job"
if phase1k_daily_job not in daily_events:
    daily_events.append(phase1k_daily_job)

scheduler_events["daily"] = daily_events
