frappe.ui.form.on("NDIS Next Governed Limited Op Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Preview Item", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Preview Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13P Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Preview Phase13P Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13P Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Preview Phase13P Guardrail Report");
        }, __("Open"));

        if (frm.doc.candidate_validation) {
            frm.add_custom_button(__("Open Phase 13O Candidate Validation"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Candidate Validation", frm.doc.candidate_validation);
            }, __("Evidence"));
        }

        if (frm.doc.preview_payment_entry) {
            frm.add_custom_button(__("Open Previewed Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.preview_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.preview_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation preview approved. Execution gate can proceed next."),
                "green"
            );
        }
    }
});
