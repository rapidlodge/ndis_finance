frappe.ui.form.on("NDIS Governed Steady State Baseline Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Baseline"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Baseline", frm.doc.baseline);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Evidence"));
        }
    }
});
