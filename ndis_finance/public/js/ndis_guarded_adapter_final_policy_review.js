frappe.ui.form.on("NDIS Guarded Adapter Final Policy Review", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Review Items"), () => {
            frappe.set_route("List", "NDIS Guarded Adapter Final Policy Review Item", {
                review: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Review Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Final Policy Review Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Final Policy Review Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 10C Freeze"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Smoke Rollback Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 10B Rollback"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Adapter Smoke Rollback", frm.doc.rollback);
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

        if (frm.doc.final_policy_review_approved) {
            frm.dashboard.set_headline_alert(
                __("Final policy review approved. Ready for final policy decision phase."),
                "green"
            );
        }
    }
});
