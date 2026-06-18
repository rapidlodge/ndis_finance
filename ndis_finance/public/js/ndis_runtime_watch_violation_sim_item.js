frappe.ui.form.on("NDIS Runtime Watch Violation Sim Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.simulation) {
            frm.add_custom_button(__("Open Simulation"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Violation Sim", frm.doc.simulation);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Evidence"));
        }
    }
});
