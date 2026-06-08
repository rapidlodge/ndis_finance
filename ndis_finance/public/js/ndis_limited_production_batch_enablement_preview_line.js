frappe.ui.form.on("NDIS Limited Production Batch Enablement Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.enablement_preview) {
            frm.add_custom_button(__("Open Enablement Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Preview", frm.doc.enablement_preview);
            }, __("Open"));
        }
    }
});
