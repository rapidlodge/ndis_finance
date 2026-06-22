frappe.ui.form.on("NDIS Governed Limited Op Candidate Validation", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Validation Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Candidate Validation Item", {
                validation: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Validation Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Candidate Validation Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Candidate Validation Guardrail Report");
        }, __("Open"));

        if (frm.doc.candidate) {
            frm.add_custom_button(__("Open Phase 11F Candidate"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Candidate", frm.doc.candidate);
            }, __("Evidence"));
        }

        if (frm.doc.candidate_validation_approved) {
            frm.dashboard.set_headline_alert(
                __("Candidate Sales Invoices validated. Preview can proceed."),
                "green"
            );
        }
    }
});
