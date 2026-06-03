frappe.ui.form.on("NDIS Controlled Production Batch Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Smoke Line", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 8D Activation"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Rollback is required. Do not continue live posting before Phase 8F rollback is completed."),
                "orange"
            );
        }
    }
});
