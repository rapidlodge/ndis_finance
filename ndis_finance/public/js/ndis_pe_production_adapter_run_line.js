frappe.ui.form.on("NDIS PE Production Adapter Run Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Adapter Run"), () => {
                frappe.set_route("Form", "NDIS PE Production Adapter Run", frm.doc.adapter_run);
            }, __("Open"));
        }

        if (frm.doc.source_preview_line) {
            frm.add_custom_button(__("Open Source Preview Line"), () => {
                frappe.set_route("Form", "NDIS PE Production Posting Preview Line", frm.doc.source_preview_line);
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
