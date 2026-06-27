frappe.ui.form.on("NDIS Next Controlled Cycle Candidate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Candidate Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Cand Item", {
                candidate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Candidate Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Candidate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Candidate Guardrail Report");
        }, __("Open"));

        if (frm.doc.design) {
            frm.add_custom_button(__("Open Phase 11Q Design"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Design", frm.doc.design);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_selection_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle candidate selection approved. Candidate validation can proceed; no posting has occurred."),
                "green"
            );
        }
    }
});
