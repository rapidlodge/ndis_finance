frappe.ui.form.on("NDIS Limited Production Batch Policy Enablement Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Enablement Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Enablement Line", {
                enablement_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Enablement Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Enablement Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Enablement Guardrail Report");
        }, __("Open"));

        if (frm.doc.readiness_gate) {
            frm.add_custom_button(__("Open Phase 9R Readiness"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Readiness Gate", frm.doc.readiness_gate);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.ready_for_limited_batch_use) {
            frm.dashboard.set_headline_alert(
                __("Controlled limited production batch policy is enabled. Live posting remains blocked."),
                "green"
            );
        }
    }
});
