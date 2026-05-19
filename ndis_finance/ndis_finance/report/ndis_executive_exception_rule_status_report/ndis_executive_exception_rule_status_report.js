frappe.query_reports["NDIS Executive Exception Rule Status Report"] = {
    filters: [
        { fieldname: "active", label: __("Active"), fieldtype: "Select", options: "\n1\n0" },
        {
            fieldname: "severity",
            label: __("Severity"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        },
        {
            fieldname: "metric_key",
            label: __("Metric Key"),
            fieldtype: "Select",
            options: "\nestimated_margin_percent\nestimated_margin\npayroll_cost_ratio\nshortfall_ratio\nopen_leakage\nopen_recovery\nunmapped_payroll_lines\nfailed_automation_runs_7_days\napproved_drafts_not_sent\nescalation_candidates\noverdue_recovery_cases\npaid_revenue\ntotal_allocated_cost\npayroll_cost\nnon_payroll_cost"
        }
    ]
};
