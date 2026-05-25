frappe.ui.form.on("NDIS PE Production Posting Policy", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Policy Register"), () => {
            frappe.set_route("query-report", "NDIS PE Production Policy Register");
        }, __("Open"));

        if (frm.doc.mapping_rule) {
            frm.add_custom_button(__("Open Mapping Rule"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Mapping Rule", frm.doc.mapping_rule);
            }, __("Open"));
        }

        if (frm.doc.production_posting_enabled) {
            frm.dashboard.set_headline_alert(
                __("Warning: production posting is enabled on this policy. Phase 5A expects this to remain disabled."),
                "red"
            );
        }
    }
});
