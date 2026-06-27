frappe.ui.form.on("NDIS Next Controlled Cycle Cand Valid", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Validation Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Cand Valid Item", {
                validation: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Validation Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Cand Valid Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Cand Valid Guardrail Report");
        }, __("Open"));

        if (frm.doc.candidate) {
            frm.add_custom_button(__("Open Phase 11R Candidate"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Candidate", frm.doc.candidate);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_validation_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle candidate validation approved. Preview gate can proceed; no posting has occurred."),
                "green"
            );
        }
    }
});
