frappe.ui.form.on("NDIS Limited Production Batch Policy Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Preview Line", {
                policy_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.policy_design) {
            frm.add_custom_button(__("Open Phase 9B Design"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Design", frm.doc.policy_design);
            }, __("Evidence"));
        }

        if (frm.doc.source_preview) {
            frm.add_custom_button(__("Open Source Preview"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Preview", frm.doc.source_preview);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_hard_block_adapter) {
            frm.dashboard.set_headline_alert(
                __("Limited policy preview is complete. Ready for hard-block adapter. Live posting remains disabled."),
                "green"
            );
        }
    }
});
