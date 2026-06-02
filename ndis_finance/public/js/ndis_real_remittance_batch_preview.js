frappe.ui.form.on("NDIS Real Remittance Batch Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch Preview Line", {
                batch_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Preview Exception Report", {
                batch_preview: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 7A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }

        if (frm.doc.evidence_freeze) {
            frm.add_custom_button(__("Open Phase 6H Freeze"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Evidence Freeze", frm.doc.evidence_freeze);
            }, __("Evidence"));
        }
    }
});
