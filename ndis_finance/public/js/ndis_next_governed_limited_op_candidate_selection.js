frappe.ui.form.on("NDIS Next Governed Limited Op Candidate Selection", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Candidate Selection Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Candidate Selection Item", {
                candidate_selection: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Candidate Selection Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13N Candidate Selection Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase13N Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13N Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase13N Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13Z Candidate Selection Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase13Z Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13Z Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase13Z Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14L Candidate Selection Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase14L Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14L Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Candidate Selection Phase14L Guardrail Report");
        }, __("Open"));

        if (frm.doc.design) {
            const design_label = frm.doc.candidate_selection_payment_entry === "ACC-PAY-2026-00016"
                ? __("Open Phase 14K Design")
                : frm.doc.candidate_selection_payment_entry === "ACC-PAY-2026-00015"
                ? __("Open Phase 13Y Design")
                : __("Open Phase 13M Design");
            frm.add_custom_button(design_label, () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Design", frm.doc.design);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        const selected_payment_entry = frm.doc.candidate_selection_payment_entry || frm.doc.monitored_payment_entry;

        if (selected_payment_entry) {
            frm.add_custom_button(__("Open Selected Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", selected_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.candidate_selection_approved) {
            frm.dashboard.set_headline_alert(
                __("Candidate selection approved. Candidate validation gate can proceed next."),
                "green"
            );
        }
    }
});
