frappe.ui.form.on("NDIS Next Controlled Cycle Rollback Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Freeze"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Rollback Freeze", frm.doc.freeze);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.frozen_payment_entry) {
            frm.add_custom_button(__("Open Frozen Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.frozen_payment_entry);
            }, __("Accounting"));
        }
    }
});
