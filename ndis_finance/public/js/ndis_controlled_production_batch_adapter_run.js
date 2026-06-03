frappe.ui.form.on("NDIS Controlled Production Batch Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Adapter Line", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Adapter Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Adapter Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Adapter Exception Report", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 8B Preview"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 8A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
