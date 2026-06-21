frappe.ui.form.on("NDIS Governed Limited Op Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Freeze Item Report", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 10X Rollback"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }
    }
});
