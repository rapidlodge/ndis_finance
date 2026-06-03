frappe.ui.form.on("NDIS Controlled Production Batch Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Activation Items"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Activation Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Activation Guardrail Report");
        }, __("Open"));

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Phase 8C Adapter"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Adapter Run", frm.doc.adapter_run);
            }, __("Evidence"));
        }

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 8B Preview"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 8A Design"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
