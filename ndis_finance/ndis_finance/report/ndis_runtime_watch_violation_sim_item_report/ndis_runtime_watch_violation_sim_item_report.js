frappe.query_reports["NDIS Runtime Watch Violation Sim Item Report"] = {
    filters: [
        {
            fieldname: "simulation",
            label: __("Simulation"),
            fieldtype: "Link",
            options: "NDIS Runtime Watch Violation Sim"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        },
        {
            fieldname: "scenario_key",
            label: __("Scenario"),
            fieldtype: "Select",
            options: "\nover_line\nover_amount\nover_payment_entry\nlive_posting\njournal_entry_side_effect\npurchase_invoice_side_effect"
        }
    ]
};
