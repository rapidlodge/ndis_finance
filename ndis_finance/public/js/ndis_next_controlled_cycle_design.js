frappe.ui.form.on("NDIS Next Controlled Cycle Design", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Design Item", {
                design: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Design Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Design Guardrail Report");
        }, __("Open"));

        if (frm.doc.planning) {
            frm.add_custom_button(__("Open Phase 11P Planning"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Planning", frm.doc.planning);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.design_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle design approved. Candidate selection can proceed; no posting has occurred."),
                "green"
            );
        }
    }
});
