frappe.ui.form.on("NDIS Next Governed Limited Op Candidate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Candidate Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Candidate Item", {
                candidate_selection: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Candidate Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Guardrail Report");
        }, __("Open"));

        if (frm.doc.design) {
            frm.add_custom_button(__("Open Phase 12C Design"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Design", frm.doc.design);
            }, __("Evidence"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_selection_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation candidate selection approved. Candidate validation gate can proceed next."),
                "green"
            );
        }
    }
});
