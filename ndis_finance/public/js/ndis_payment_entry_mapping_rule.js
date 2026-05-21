frappe.ui.form.on("NDIS Payment Entry Mapping Rule", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Mapping Report"), () => {
            frappe.set_route("query-report", "NDIS Payment Entry Mapping Rule Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Allocation Previews"), () => {
            frappe.set_route("List", "NDIS Payment Entry Allocation Preview", {
                mapping_rule: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.last_preview) {
            frm.add_custom_button(__("Open Last Preview"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Allocation Preview", frm.doc.last_preview);
            }, __("Open"));
        }
    }
});
