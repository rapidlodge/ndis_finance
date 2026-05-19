frappe.ui.form.on("NDIS Accounting Posting Policy", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Previews"), () => {
            frappe.set_route("List", "NDIS Accounting Posting Preview", {
                policy: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Policy Register"), () => {
            frappe.set_route("query-report", "NDIS Accounting Posting Policy Register Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Accounting Posting Preview Report");
        }, __("Open"));
    }
});
