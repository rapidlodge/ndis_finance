frappe.ui.form.on("NDIS Real Remittance PE Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Preview Line", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Preview Line Report", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Preview Exception Report", {
                preview: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 6A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }

        if (frm.doc.source_remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.source_remittance_import);
            }, __("Evidence"));
        }
    }
});
