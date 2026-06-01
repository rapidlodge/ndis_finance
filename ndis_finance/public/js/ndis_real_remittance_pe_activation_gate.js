frappe.ui.form.on("NDIS Real Remittance PE Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Activation Exception Report", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Readiness Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Activation Readiness Report");
        }, __("Open"));

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Phase 6C Adapter"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Adapter Run", frm.doc.adapter_run);
            }, __("Evidence"));
        }

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 6B Preview"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 6A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
