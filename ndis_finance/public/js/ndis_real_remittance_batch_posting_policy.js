frappe.ui.form.on("NDIS Real Remittance Batch Posting Policy", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Policy Register"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Policy Register Report");
        }, __("Open"));
    }
});
