frappe.ui.form.on("NDIS Next Governed Limited Op Candidate Validation", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Candidate Validation Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Candidate Validation Item", {
                candidate_validation: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Candidate Validation Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Validation Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Validation Guardrail Report");
        }, __("Open"));

        if (frm.doc.candidate_selection) {
            frm.add_custom_button(__("Open Phase 12P Candidate Selection"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Candidate Selection", frm.doc.candidate_selection);
            }, __("Evidence"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_validation_approved) {
            frm.dashboard.set_headline_alert(
                __("Candidate validation approved. Preview gate can proceed next."),
                "green"
            );
        }
    }
});
