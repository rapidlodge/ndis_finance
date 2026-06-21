frappe.ui.form.on("NDIS Governed Limited Op Closeout", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Closeout Item", { closeout: frm.doc.name });
        }, __("Open"));

        frm.add_custom_button(__("Open Closeout Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Closeout Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Closeout Item Report", { closeout: frm.doc.name });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Closeout Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 10Y Freeze"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }
    }
});
