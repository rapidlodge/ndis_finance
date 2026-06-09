frappe.ui.form.on("NDIS Limited Production Batch Enablement Readiness Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.readiness_gate) {
            frm.add_custom_button(__("Open Readiness Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Readiness Gate", frm.doc.readiness_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
