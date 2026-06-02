frappe.ui.form.on("NDIS Real Remittance Batch Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch Adapter Run Line", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Adapter Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Adapter Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Adapter Guardrail Report");
        }, __("Open"));

        if (frm.doc.batch_preview) {
            frm.add_custom_button(__("Open Phase 7B Preview"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Preview", frm.doc.batch_preview);
            }, __("Evidence"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 7A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
