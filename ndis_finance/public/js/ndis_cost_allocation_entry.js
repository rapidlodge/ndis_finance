frappe.ui.form.on("NDIS Cost Allocation Entry", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.cost_pool) {
            frm.add_custom_button(__("Open Cost Pool"), () => {
                frappe.set_route("Form", "NDIS Cost Pool", frm.doc.cost_pool);
            }, __("Open"));
        }

        if (frm.doc.house) {
            frm.add_custom_button(__("Open House"), () => {
                frappe.set_route("Form", "NDIS House", frm.doc.house);
            }, __("Open"));
        }

        if (frm.doc.participant) {
            frm.add_custom_button(__("Open Participant"), () => {
                frappe.set_route("Form", "Customer", frm.doc.participant);
            }, __("Open"));
        }
    },
});
