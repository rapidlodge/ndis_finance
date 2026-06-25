frappe.ui.form.on("NDIS Post Closeout Steady Baseline Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Baseline"), () => {
                frappe.set_route("Form", "NDIS Post Closeout Steady Baseline", frm.doc.baseline);
            }, __("Open"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
