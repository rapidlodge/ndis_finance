frappe.ui.form.on("NDIS Next Controlled Cycle Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Preview Item", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.validation) {
            frm.add_custom_button(__("Open Phase 11S Validation"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Cand Valid", frm.doc.validation);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.preview_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle preview approved. Execution gate can proceed; no posting has occurred."),
                "green"
            );
        }
    }
});
