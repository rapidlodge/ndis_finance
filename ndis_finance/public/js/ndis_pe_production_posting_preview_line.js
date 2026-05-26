frappe.ui.form.on("NDIS PE Production Posting Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.posting_preview) {
            frm.add_custom_button(__("Open Posting Preview"), () => {
                frappe.set_route("Form", "NDIS PE Production Posting Preview", frm.doc.posting_preview);
            }, __("Open"));
        }

        if (frm.doc.posting_policy) {
            frm.add_custom_button(__("Open Posting Policy"), () => {
                frappe.set_route("Form", "NDIS PE Production Posting Policy", frm.doc.posting_policy);
            }, __("Open"));
        }

        if (frm.doc.mapping_rule) {
            frm.add_custom_button(__("Open Mapping Rule"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Mapping Rule", frm.doc.mapping_rule);
            }, __("Open"));
        }
    }
});
