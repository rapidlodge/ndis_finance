frappe.ui.form.on("NDIS Next Controlled Cycle Design Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.design) {
            frm.add_custom_button(__("Open Design"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Design", frm.doc.design);
            }, __("Open"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }
    }
});
