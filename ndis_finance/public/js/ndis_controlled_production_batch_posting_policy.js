frappe.ui.form.on("NDIS Controlled Production Batch Posting Policy", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Open Policy Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Policy Report");
        }, __("Open"));
        if (frm.doc.production_batch_enabled || frm.doc.live_posting_allowed) {
            frm.dashboard.set_headline_alert(__("Warning: this policy is live-enabled. Phase 8A expects all live flags to remain off."), "red");
        }
    }
});
