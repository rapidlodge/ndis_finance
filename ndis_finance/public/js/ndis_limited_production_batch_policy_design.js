frappe.ui.form.on("NDIS Limited Production Batch Policy Design", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Design Item", {
                policy_design: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Design Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Design Guardrail Report");
        }, __("Open"));

        if (frm.doc.policy_review_gate) {
            frm.add_custom_button(__("Open Phase 9A Review"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Policy Review Gate", frm.doc.policy_review_gate);
            }, __("Evidence"));
        }

        if (frm.doc.phase8g_freeze) {
            frm.add_custom_button(__("Open Phase 8G Freeze"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Evidence Freeze", frm.doc.phase8g_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_policy_preview) {
            frm.dashboard.set_headline_alert(
                __("Limited policy design is complete. Ready for preview phase. Live posting remains disabled."),
                "green"
            );
        }
    }
});
