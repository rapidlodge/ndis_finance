frappe.ui.form.on("NDIS Controlled Production Batch Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Preview Line", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Preview Exception Report");
        }, __("Open"));

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 8A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
