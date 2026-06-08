frappe.ui.form.on("NDIS Limited Production Batch Enablement Adapter Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.enablement_adapter) {
            frm.add_custom_button(__("Open Enablement Adapter"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Adapter Run", frm.doc.enablement_adapter);
            }, __("Open"));
        }
    }
});
