frappe.ui.form.on("NDIS Limited Production Batch Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Smoke Run Line", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Controlled Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Controlled Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 9E Activation Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Controlled smoke submitted. Rollback is now required before freeze."),
                "orange"
            );
        }
    }
});
