frappe.ui.form.on("NDIS Limited Production Batch Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Adapter Run Line", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Adapter Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Adapter Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Adapter Guardrail Report");
        }, __("Open"));

        if (frm.doc.policy_preview) {
            frm.add_custom_button(__("Open Phase 9C Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Preview", frm.doc.policy_preview);
            }, __("Evidence"));
        }

        if (frm.doc.policy_design) {
            frm.add_custom_button(__("Open Phase 9B Design"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Design", frm.doc.policy_design);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_activation_gate) {
            frm.dashboard.set_headline_alert(
                __("Adapter hard-block evidence complete. Ready for limited activation gate. Live posting remains disabled."),
                "green"
            );
        }
    }
});
