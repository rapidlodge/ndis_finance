frappe.ui.form.on("NDIS Governed Steady State Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Monitor Items"), () => {
            frappe.set_route("List", "NDIS Governed Steady State Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Monitor Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Steady State Monitor Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Steady State Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 11A Baseline"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }
    }
});
