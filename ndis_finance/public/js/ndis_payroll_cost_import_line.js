frappe.ui.form.on("NDIS Payroll Cost Import Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.payroll_cost_import) {
            frm.add_custom_button(__("Open Payroll Cost Import"), () => {
                frappe.set_route("Form", "NDIS Payroll Cost Import", frm.doc.payroll_cost_import);
            }, __("Open"));
        }

        if (frm.doc.au_payroll_run_log) {
            frm.add_custom_button(__("Open AU Payroll Run"), () => {
                frappe.set_route("Form", "AU Payroll Run Log", frm.doc.au_payroll_run_log);
            }, __("Open"));
        }

        if (frm.doc.cost_pool) {
            frm.add_custom_button(__("Open Cost Pool"), () => {
                frappe.set_route("Form", "NDIS Cost Pool", frm.doc.cost_pool);
            }, __("Open"));
        }

        if (frm.doc.employee) {
            frm.add_custom_button(__("Open Employee"), () => {
                frappe.set_route("Form", "Employee", frm.doc.employee);
            }, __("Open"));
        }

        if (frm.doc.house) {
            frm.add_custom_button(__("Open House"), () => {
                frappe.set_route("Form", "NDIS House", frm.doc.house);
            }, __("Open"));
        }
    },
});
