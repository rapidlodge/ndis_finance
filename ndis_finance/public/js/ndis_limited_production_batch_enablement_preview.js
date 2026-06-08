frappe.ui.form.on("NDIS Limited Production Batch Enablement Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Preview Line", {
                enablement_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.enablement_gate) {
            frm.add_custom_button(__("Open Phase 9K Enablement Design"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Design Gate", frm.doc.enablement_gate);
            }, __("Evidence"));
        }

        if (frm.doc.policy_lock) {
            frm.add_custom_button(__("Open Phase 9J Policy Lock"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Lock", frm.doc.policy_lock);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_enablement_adapter) {
            frm.dashboard.set_headline_alert(
                __("Enablement preview approved. Ready for limited hard-block adapter. No policy has been enabled."),
                "green"
            );
        }
    }
});
