frappe.ui.form.on("NDIS Limited Production Batch Enablement Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Smoke Line", {
                enablement_smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 9N Activation Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Limited policy enabled for smoke only. Rollback is now required before freeze."),
                "orange"
            );
        }
    }
});
