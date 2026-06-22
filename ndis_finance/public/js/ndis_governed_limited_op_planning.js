frappe.ui.form.on("NDIS Governed Limited Op Planning", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Planning Item", {
                planning: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Planning Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Planning Item Report", {
                planning: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Planning Guardrail Report");
        }, __("Open"));

        if (frm.doc.planning_approved) {
            frm.dashboard.add_indicator(__("Planning Approved - No Posting"), "green");
        }

        if (frm.doc.precheck) {
            frm.add_custom_button(__("Open Phase 11C Precheck"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Precheck", frm.doc.precheck);
            }, __("Evidence"));
        }

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Phase 11B Monitor"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 11A Baseline"), () => {
                frappe.set_route("Form", "NDIS Governed Steady State Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }
    }
});
