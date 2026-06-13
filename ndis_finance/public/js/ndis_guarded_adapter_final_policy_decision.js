frappe.ui.form.on("NDIS Guarded Adapter Final Policy Decision", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Decision Items"), () => {
            frappe.set_route("List", "NDIS Guarded Adapter Final Policy Decision Item", {
                decision: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Decision Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Final Policy Decision Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Final Policy Decision Guardrail Report");
        }, __("Open"));

        if (frm.doc.review) {
            frm.add_custom_button(__("Open Phase 10D Review"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Final Policy Review", frm.doc.review);
            }, __("Evidence"));
        }

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 10C Freeze"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Smoke Rollback Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.final_policy_decision_applied) {
            frm.dashboard.set_headline_alert(
                __("Final decision applied: controlled limited operation remains enabled, live posting remains blocked."),
                "green"
            );
        }
    }
});
