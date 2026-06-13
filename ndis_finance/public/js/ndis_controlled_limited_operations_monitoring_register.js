frappe.ui.form.on("NDIS Controlled Limited Operations Monitoring Register", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Register Items"), () => {
            frappe.set_route("List", "NDIS Controlled Limited Operations Monitoring Register Item", {
                register: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Register Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Operations Monitoring Register Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Operations Monitoring Register Guardrail Report");
        }, __("Open"));

        if (frm.doc.decision) {
            frm.add_custom_button(__("Open Phase 10E Decision"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Final Policy Decision", frm.doc.decision);
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

        if (frm.doc.monitoring_register_active) {
            frm.dashboard.set_headline_alert(
                __("Controlled limited operations monitoring is active. Live posting remains blocked."),
                "green"
            );
        }
    }
});
