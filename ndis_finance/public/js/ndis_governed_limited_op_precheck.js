frappe.ui.form.on("NDIS Governed Limited Op Precheck", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Precheck Item", {
                precheck: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Precheck Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Precheck Item Report", {
                precheck: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Precheck Guardrail Report");
        }, __("Open"));

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Phase 11B Monitor"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 11A Baseline"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }
    }
});
