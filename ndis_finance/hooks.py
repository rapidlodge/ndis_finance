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
        "before_submit": "ndis_finance.services.sandbox_invoice_test_harness.block_unacknowledged_sandbox_sales_invoice_submit",
        "on_submit": "ndis_finance.services.budget_control.update_usage_from_sales_invoice",
        "before_cancel": "ndis_finance.services.claim_batch_engine.before_sales_invoice_cancel",
        "on_cancel": "ndis_finance.services.claim_batch_engine.on_sales_invoice_cancelled",
    },
    "Journal Entry": {
        "before_submit": "ndis_finance.services.sandbox_accounting_posting.block_sandbox_journal_entry_submit",
    },
    "Payment Entry": {
        "before_submit": "ndis_finance.services.sandbox_payment_entry_posting.block_sandbox_payment_entry_submit",
    },
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
                    "NDIS True House Profitability Report",
                    "NDIS True Participant Profitability Report",
                    "NDIS Cost Type Analysis Report",
                    "NDIS Profitability Summary Report",
                    "NDIS Payroll Cost Import Reconciliation Report",
                    "NDIS Payroll Cost by House Report",
                    "NDIS Payroll Cost by Participant Report",
                    "NDIS Payroll Profitability Impact Report",
                    "NDIS Profitability Executive Dashboard",
                    "NDIS Executive KPI Trend Report",
                    "NDIS Executive Snapshot Detail Report",
                    "NDIS Executive Exception Register Report",
                    "NDIS Executive Exception Rule Status Report",
                    "NDIS Executive Action Plan Register Report",
                    "NDIS Executive Action Plan Overdue Report",
                    "NDIS Executive Governance Pack Report",
                    "NDIS Governance Pack Detail Report",
                    "NDIS Finance Production Readiness Report",
                    "NDIS Finance Readiness Exception Report",
                    "NDIS Accounting Posting Policy Register Report",
                    "NDIS Accounting Posting Preview Report",
                    "NDIS Accounting Posting Request Register Report",
                    "NDIS Accounting Posting Request Line Report",
                    "NDIS Sandbox Accounting Posting Run Report",
                    "NDIS Sandbox Accounting Posting Run Line Report",
                    "NDIS Sandbox Accounting Cleanup Report",
                    "NDIS Sandbox Journal Entry Hygiene Report",
                    "NDIS Accounting Sandbox Completion Gate Report",
                    "NDIS Accounting Sandbox Completion Exception Report",
                    "NDIS Accounting Design Matrix Report",
                    "NDIS Accounting Design Review Report",
                    "NDIS Accounting Design Exception Report",
                    "NDIS Payment Entry Mapping Rule Report",
                    "NDIS Payment Entry Allocation Preview Report",
                    "NDIS Payment Entry Allocation Exception Report",
                    "NDIS Sandbox Payment Entry Run Report",
                    "NDIS Sandbox Payment Entry Run Line Report",
                    "NDIS Sandbox Payment Entry Cleanup Report",
                    "NDIS Sandbox Payment Entry Hygiene Report",
                    "NDIS Payment Entry Sandbox Completion Gate Report",
                    "NDIS Payment Entry Sandbox Completion Exception Report",
                    "NDIS Sandbox Invoice Test Run Report",
                    "NDIS Sandbox Invoice Test Line Report",
                    "NDIS Invoice Backed PE Smoke Run Report",
                    "NDIS Invoice Backed PE Smoke Line Report",
                    "NDIS Sandbox Accounting Cleanup Pack Report",
                    "NDIS Sandbox Accounting Cleanup Line Report",
                    "NDIS Sandbox Accounting Hygiene Report",
                    "NDIS PE Sandbox Readiness Freeze Report",
                    "NDIS PE Sandbox Readiness Freeze Item Report",
                    "NDIS PE Production Policy Register",
                    "NDIS PE Production Design Gate Report",
                    "NDIS PE Production Design Exception Report",
                    "NDIS PE Production Account Mapping Gate Report",
                    "NDIS PE Production Account Mapping Exception Report",
                    "NDIS PE Production Mapping Control Report",
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
                    "NDIS Payroll Cost Import",
                    "NDIS Payroll Cost Import Line",
                    "NDIS Executive Dashboard Snapshot",
                    "NDIS Executive Dashboard Snapshot Metric",
                    "NDIS Executive Exception Rule",
                    "NDIS Executive Exception Alert",
                    "NDIS Executive Exception Action Plan",
                    "NDIS Executive Exception Action Step",
                    "NDIS Executive Governance Pack",
                    "NDIS Executive Governance Pack Item",
                    "NDIS Finance Production Readiness Check",
                    "NDIS Finance Production Readiness Check Item",
                    "NDIS Accounting Posting Policy",
                    "NDIS Accounting Posting Preview",
                    "NDIS Accounting Posting Preview Line",
                    "NDIS Accounting Posting Request",
                    "NDIS Accounting Posting Request Line",
                    "NDIS Sandbox Accounting Posting Run",
                    "NDIS Sandbox Accounting Posting Run Line",
                    "NDIS Sandbox Accounting Cleanup Run",
                    "NDIS Sandbox Accounting Cleanup Line",
                    "NDIS Accounting Sandbox Completion Gate",
                    "NDIS Accounting Sandbox Completion Gate Item",
                    "NDIS Accounting Design Matrix",
                    "NDIS Accounting Design Review",
                    "NDIS Accounting Design Review Item",
                    "NDIS Payment Entry Mapping Rule",
                    "NDIS Payment Entry Allocation Preview",
                    "NDIS Payment Entry Allocation Preview Line",
                    "NDIS Sandbox Payment Entry Run",
                    "NDIS Sandbox Payment Entry Run Line",
                    "NDIS Sandbox Payment Entry Cleanup Run",
                    "NDIS Sandbox Payment Entry Cleanup Line",
                    "NDIS Payment Entry Sandbox Completion Gate",
                    "NDIS Payment Entry Sandbox Completion Gate Item",
                    "NDIS Sandbox Invoice Test Run",
                    "NDIS Sandbox Invoice Test Line",
                    "NDIS Invoice Backed PE Smoke Run",
                    "NDIS Invoice Backed PE Smoke Line",
                    "NDIS Sandbox Accounting Cleanup Pack",
                    "NDIS Sandbox Accounting Cleanup Pack Line",
                    "NDIS PE Sandbox Readiness Freeze",
                    "NDIS PE Sandbox Readiness Freeze Item",
                    "NDIS PE Production Posting Policy",
                    "NDIS PE Production Design Gate",
                    "NDIS PE Production Design Gate Item",
                    "NDIS PE Production Account Mapping Gate",
                    "NDIS PE Production Account Mapping Gate Item",
                ],
            ]
        ],
    },
    {
        "dt": "NDIS PE Production Posting Policy",
        "filters": [["policy_id", "like", "NDIS-PE-POLICY-%"]],
    },
    {
        "dt": "NDIS Executive Exception Rule",
        "filters": [["name", "like", "NDIS-EXEC-RULE-%"]],
    },
    {
        "dt": "NDIS Accounting Posting Policy",
        "filters": [["name", "like", "NDIS-ACC-POLICY-%"]],
    },
    {
        "dt": "NDIS Accounting Design Matrix",
        "filters": [["name", "like", "NDIS-ACC-DESIGN-%"]],
    },
    {
        "dt": "NDIS Payment Entry Mapping Rule",
        "filters": [["name", "like", "NDIS-PE-MAP-%"]],
    },
    {
        "dt": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Payment Entry-custom_ndis_sandbox_pe_section",
                    "Payment Entry-custom_ndis_sandbox_payment_entry_run",
                    "Payment Entry-custom_ndis_payment_entry_allocation_preview",
                    "Payment Entry-custom_ndis_sandbox_payment_entry_draft_only",
                    "Payment Entry-custom_ndis_sandbox_payment_entry_acknowledgement",
                    "Customer-custom_ndis_sandbox_customer",
                    "Customer-custom_ndis_sandbox_invoice_test_run",
                    "Item-custom_ndis_sandbox_item",
                    "Item-custom_ndis_sandbox_invoice_test_run",
                    "Sales Invoice-custom_ndis_sandbox_invoice_section",
                    "Sales Invoice-custom_ndis_sandbox_test_invoice",
                    "Sales Invoice-custom_ndis_sandbox_invoice_test_run",
                    "Sales Invoice-custom_ndis_sandbox_invoice_acknowledgement",
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
        "NDIS Payroll Cost Import": "public/js/ndis_payroll_cost_import.js",
        "NDIS Payroll Cost Import Line": "public/js/ndis_payroll_cost_import_line.js",
        "NDIS Executive Dashboard Snapshot": "public/js/ndis_executive_dashboard_snapshot.js",
        "NDIS Executive Dashboard Snapshot Metric": "public/js/ndis_executive_dashboard_snapshot_metric.js",
        "NDIS Executive Exception Rule": "public/js/ndis_executive_exception_rule.js",
        "NDIS Executive Exception Alert": "public/js/ndis_executive_exception_alert.js",
        "NDIS Executive Exception Action Plan": "public/js/ndis_executive_exception_action_plan.js",
        "NDIS Executive Exception Action Step": "public/js/ndis_executive_exception_action_step.js",
        "NDIS Executive Governance Pack": "public/js/ndis_executive_governance_pack.js",
        "NDIS Executive Governance Pack Item": "public/js/ndis_executive_governance_pack_item.js",
        "NDIS Finance Production Readiness Check": "public/js/ndis_finance_production_readiness_check.js",
        "NDIS Finance Production Readiness Check Item": "public/js/ndis_finance_production_readiness_check_item.js",
        "NDIS Accounting Posting Policy": "public/js/ndis_accounting_posting_policy.js",
        "NDIS Accounting Posting Preview": "public/js/ndis_accounting_posting_preview.js",
        "NDIS Accounting Posting Preview Line": "public/js/ndis_accounting_posting_preview_line.js",
        "NDIS Accounting Posting Request": "public/js/ndis_accounting_posting_request.js",
        "NDIS Accounting Posting Request Line": "public/js/ndis_accounting_posting_request_line.js",
        "NDIS Sandbox Accounting Posting Run": "public/js/ndis_sandbox_accounting_posting_run.js",
        "NDIS Sandbox Accounting Posting Run Line": "public/js/ndis_sandbox_accounting_posting_run_line.js",
        "NDIS Sandbox Accounting Cleanup Run": "public/js/ndis_sandbox_accounting_cleanup_run.js",
        "NDIS Sandbox Accounting Cleanup Line": "public/js/ndis_sandbox_accounting_cleanup_line.js",
        "NDIS Accounting Sandbox Completion Gate": "public/js/ndis_accounting_sandbox_completion_gate.js",
        "NDIS Accounting Sandbox Completion Gate Item": "public/js/ndis_accounting_sandbox_completion_gate_item.js",
        "NDIS Accounting Design Matrix": "public/js/ndis_accounting_design_matrix.js",
        "NDIS Accounting Design Review": "public/js/ndis_accounting_design_review.js",
        "NDIS Accounting Design Review Item": "public/js/ndis_accounting_design_review_item.js",
        "NDIS Payment Entry Mapping Rule": "public/js/ndis_payment_entry_mapping_rule.js",
        "NDIS Payment Entry Allocation Preview": "public/js/ndis_payment_entry_allocation_preview.js",
        "NDIS Payment Entry Allocation Preview Line": "public/js/ndis_payment_entry_allocation_preview_line.js",
        "NDIS Sandbox Payment Entry Run": "public/js/ndis_sandbox_payment_entry_run.js",
        "NDIS Sandbox Payment Entry Run Line": "public/js/ndis_sandbox_payment_entry_run_line.js",
        "NDIS Sandbox Payment Entry Cleanup Run": "public/js/ndis_sandbox_payment_entry_cleanup_run.js",
        "NDIS Sandbox Payment Entry Cleanup Line": "public/js/ndis_sandbox_payment_entry_cleanup_line.js",
        "NDIS Payment Entry Sandbox Completion Gate": "public/js/ndis_payment_entry_sandbox_completion_gate.js",
        "NDIS Payment Entry Sandbox Completion Gate Item": "public/js/ndis_payment_entry_sandbox_completion_gate_item.js",
        "NDIS Sandbox Invoice Test Run": "public/js/ndis_sandbox_invoice_test_run.js",
        "NDIS Sandbox Invoice Test Line": "public/js/ndis_sandbox_invoice_test_line.js",
        "NDIS Invoice Backed PE Smoke Run": "public/js/ndis_invoice_backed_pe_smoke_run.js",
        "NDIS Invoice Backed PE Smoke Line": "public/js/ndis_invoice_backed_pe_smoke_line.js",
        "NDIS Sandbox Accounting Cleanup Pack": "public/js/ndis_sandbox_accounting_cleanup_pack.js",
        "NDIS Sandbox Accounting Cleanup Pack Line": "public/js/ndis_sandbox_accounting_cleanup_pack_line.js",
        "NDIS PE Sandbox Readiness Freeze": "public/js/ndis_pe_sandbox_readiness_freeze.js",
        "NDIS PE Sandbox Readiness Freeze Item": "public/js/ndis_pe_sandbox_readiness_freeze_item.js",
        "NDIS PE Production Posting Policy": "public/js/ndis_pe_production_posting_policy.js",
        "NDIS PE Production Design Gate": "public/js/ndis_pe_production_design_gate.js",
        "NDIS PE Production Design Gate Item": "public/js/ndis_pe_production_design_gate_item.js",
        "NDIS PE Production Account Mapping Gate": "public/js/ndis_pe_production_account_mapping_gate.js",
        "NDIS PE Production Account Mapping Gate Item": "public/js/ndis_pe_production_account_mapping_gate_item.js",
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
        "NDIS Payroll Cost Import": "public/js/ndis_payroll_cost_import_list.js",
        "NDIS Payroll Cost Import Line": "public/js/ndis_payroll_cost_import_line_list.js",
        "NDIS Executive Dashboard Snapshot": "public/js/ndis_executive_dashboard_snapshot_list.js",
        "NDIS Executive Dashboard Snapshot Metric": "public/js/ndis_executive_dashboard_snapshot_metric_list.js",
        "NDIS Executive Exception Rule": "public/js/ndis_executive_exception_rule_list.js",
        "NDIS Executive Exception Alert": "public/js/ndis_executive_exception_alert_list.js",
        "NDIS Executive Exception Action Plan": "public/js/ndis_executive_exception_action_plan_list.js",
        "NDIS Executive Exception Action Step": "public/js/ndis_executive_exception_action_step_list.js",
        "NDIS Executive Governance Pack": "public/js/ndis_executive_governance_pack_list.js",
        "NDIS Executive Governance Pack Item": "public/js/ndis_executive_governance_pack_item_list.js",
        "NDIS Finance Production Readiness Check": "public/js/ndis_finance_production_readiness_check_list.js",
        "NDIS Finance Production Readiness Check Item": "public/js/ndis_finance_production_readiness_check_item_list.js",
        "NDIS Accounting Posting Policy": "public/js/ndis_accounting_posting_policy_list.js",
        "NDIS Accounting Posting Preview": "public/js/ndis_accounting_posting_preview_list.js",
        "NDIS Accounting Posting Preview Line": "public/js/ndis_accounting_posting_preview_line_list.js",
        "NDIS Accounting Posting Request": "public/js/ndis_accounting_posting_request_list.js",
        "NDIS Accounting Posting Request Line": "public/js/ndis_accounting_posting_request_line_list.js",
        "NDIS Sandbox Accounting Posting Run": "public/js/ndis_sandbox_accounting_posting_run_list.js",
        "NDIS Sandbox Accounting Posting Run Line": "public/js/ndis_sandbox_accounting_posting_run_line_list.js",
        "NDIS Sandbox Accounting Cleanup Run": "public/js/ndis_sandbox_accounting_cleanup_run_list.js",
        "NDIS Sandbox Accounting Cleanup Line": "public/js/ndis_sandbox_accounting_cleanup_line_list.js",
        "NDIS Accounting Sandbox Completion Gate": "public/js/ndis_accounting_sandbox_completion_gate_list.js",
        "NDIS Accounting Sandbox Completion Gate Item": "public/js/ndis_accounting_sandbox_completion_gate_item_list.js",
        "NDIS Accounting Design Matrix": "public/js/ndis_accounting_design_matrix_list.js",
        "NDIS Accounting Design Review": "public/js/ndis_accounting_design_review_list.js",
        "NDIS Accounting Design Review Item": "public/js/ndis_accounting_design_review_item_list.js",
        "NDIS Payment Entry Mapping Rule": "public/js/ndis_payment_entry_mapping_rule_list.js",
        "NDIS Payment Entry Allocation Preview": "public/js/ndis_payment_entry_allocation_preview_list.js",
        "NDIS Payment Entry Allocation Preview Line": "public/js/ndis_payment_entry_allocation_preview_line_list.js",
        "NDIS Sandbox Payment Entry Run": "public/js/ndis_sandbox_payment_entry_run_list.js",
        "NDIS Sandbox Payment Entry Run Line": "public/js/ndis_sandbox_payment_entry_run_line_list.js",
        "NDIS Sandbox Payment Entry Cleanup Run": "public/js/ndis_sandbox_payment_entry_cleanup_run_list.js",
        "NDIS Sandbox Payment Entry Cleanup Line": "public/js/ndis_sandbox_payment_entry_cleanup_line_list.js",
        "NDIS Payment Entry Sandbox Completion Gate": "public/js/ndis_payment_entry_sandbox_completion_gate_list.js",
        "NDIS Payment Entry Sandbox Completion Gate Item": "public/js/ndis_payment_entry_sandbox_completion_gate_item_list.js",
        "NDIS Sandbox Invoice Test Run": "public/js/ndis_sandbox_invoice_test_run_list.js",
        "NDIS Sandbox Invoice Test Line": "public/js/ndis_sandbox_invoice_test_line_list.js",
        "NDIS Invoice Backed PE Smoke Run": "public/js/ndis_invoice_backed_pe_smoke_run_list.js",
        "NDIS Invoice Backed PE Smoke Line": "public/js/ndis_invoice_backed_pe_smoke_line_list.js",
        "NDIS Sandbox Accounting Cleanup Pack": "public/js/ndis_sandbox_accounting_cleanup_pack_list.js",
        "NDIS Sandbox Accounting Cleanup Pack Line": "public/js/ndis_sandbox_accounting_cleanup_pack_line_list.js",
        "NDIS PE Sandbox Readiness Freeze": "public/js/ndis_pe_sandbox_readiness_freeze_list.js",
        "NDIS PE Sandbox Readiness Freeze Item": "public/js/ndis_pe_sandbox_readiness_freeze_item_list.js",
        "NDIS PE Production Posting Policy": "public/js/ndis_pe_production_posting_policy_list.js",
        "NDIS PE Production Design Gate": "public/js/ndis_pe_production_design_gate_list.js",
        "NDIS PE Production Design Gate Item": "public/js/ndis_pe_production_design_gate_item_list.js",
        "NDIS PE Production Account Mapping Gate": "public/js/ndis_pe_production_account_mapping_gate_list.js",
        "NDIS PE Production Account Mapping Gate Item": "public/js/ndis_pe_production_account_mapping_gate_item_list.js",
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

phase1w_daily_job = "ndis_finance.services.executive_snapshots.daily_executive_dashboard_snapshot_job"
if phase1w_daily_job not in daily_events:
    daily_events.append(phase1w_daily_job)

phase1x_daily_job = "ndis_finance.services.executive_exceptions.daily_executive_exception_evaluation_job"
if phase1x_daily_job not in daily_events:
    daily_events.append(phase1x_daily_job)

phase1y_daily_job = "ndis_finance.services.executive_action_plans.daily_action_plan_overdue_monitor_job"
if phase1y_daily_job not in daily_events:
    daily_events.append(phase1y_daily_job)

scheduler_events["daily"] = daily_events
