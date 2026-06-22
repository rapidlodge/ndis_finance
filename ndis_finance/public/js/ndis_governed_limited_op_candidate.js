frappe.ui.form.on("NDIS Governed Limited Op Candidate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Candidate Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Candidate Item", {
                candidate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Candidate Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Candidate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Candidate Guardrail Report");
        }, __("Open"));

        if (frm.doc.design) {
            frm.add_custom_button(__("Open Phase 11E Design"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Design", frm.doc.design);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Historical Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_selection_approved) {
            frm.dashboard.set_headline_alert(
                __("Candidate Sales Invoices selected and locked. Candidate validation can proceed."),
                "green"
            );
        }
    }
});
