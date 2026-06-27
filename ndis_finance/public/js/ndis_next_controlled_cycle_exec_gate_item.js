frappe.ui.form.on("NDIS Next Controlled Cycle Exec Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Exec Gate", frm.doc.execution_gate);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }
    }
});
