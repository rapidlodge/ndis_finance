frappe.ui.form.on("NDIS Limited Production Batch Policy Finalisation Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.finalisation_gate) {
            frm.add_custom_button(__("Open Finalisation Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Finalisation Gate", frm.doc.finalisation_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});