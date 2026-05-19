frappe.ui.form.on("NDIS Executive Dashboard Snapshot Metric", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.snapshot) {
            frm.add_custom_button(__("Open Snapshot"), () => {
                frappe.set_route("Form", "NDIS Executive Dashboard Snapshot", frm.doc.snapshot);
            }, __("Open"));
        }
    }
});
