frappe.ui.form.on("NDIS Limited Production Batch Enablement Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Activation Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Activation Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.enablement_adapter) {
            frm.add_custom_button(__("Open Phase 9M Adapter"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Adapter Run", frm.doc.enablement_adapter);
            }, __("Evidence"));
        }

        if (frm.doc.enablement_preview) {
            frm.add_custom_button(__("Open Phase 9L Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Preview", frm.doc.enablement_preview);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_enablement_smoke) {
            frm.dashboard.set_headline_alert(
                __("Activation gate allowed. Ready for limited controlled enablement smoke. No policy has been enabled."),
                "green"
            );
        }
    }
});