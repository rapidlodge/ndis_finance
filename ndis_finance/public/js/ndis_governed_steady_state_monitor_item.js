frappe.ui.form.on("NDIS Governed Steady State Monitor Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Monitor"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Monitor", frm.doc.monitor);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
