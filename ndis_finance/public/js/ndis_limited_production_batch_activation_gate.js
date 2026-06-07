frappe.ui.form.on("NDIS Limited Production Batch Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Activation Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Activation Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Phase 9D Adapter"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Adapter Run", frm.doc.adapter_run);
            }, __("Evidence"));
        }

        if (frm.doc.policy_preview) {
            frm.add_custom_button(__("Open Phase 9C Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Preview", frm.doc.policy_preview);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_batch_smoke) {
            frm.dashboard.set_headline_alert(
                __("Limited activation allowed for controlled batch smoke only. Live posting remains disabled."),
                "green"
            );
        }
    }
});
