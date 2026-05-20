frappe.ui.form.on("NDIS Accounting Design Matrix", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Matrix Report"), () => {
            frappe.set_route("query-report", "NDIS Accounting Design Matrix Report");
        }, __("Open"));

        if (frm.doc.last_review) {
            frm.add_custom_button(__("Open Last Review"), () => {
                frappe.set_route("Form", "NDIS Accounting Design Review", frm.doc.last_review);
            }, __("Open"));
        }
    }
});
