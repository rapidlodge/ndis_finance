frappe.ui.form.on("NDIS Limited Production Batch Enablement Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Adapter Line", {
                enablement_adapter: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Adapter Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Adapter Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Adapter Guardrail Report");
        }, __("Open"));

        if (frm.doc.enablement_preview) {
            frm.add_custom_button(__("Open Phase 9L Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Preview", frm.doc.enablement_preview);
            }, __("Evidence"));
        }

        if (frm.doc.enablement_gate) {
            frm.add_custom_button(__("Open Phase 9K Design"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Design Gate", frm.doc.enablement_gate);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_enablement_activation_gate) {
            frm.dashboard.set_headline_alert(
                __("Enablement hard-block adapter complete. Ready for limited enablement activation gate. No policy has been enabled."),
                "green"
            );
        }
    }
});
