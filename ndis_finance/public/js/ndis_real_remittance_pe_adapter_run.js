frappe.ui.form.on("NDIS Real Remittance PE Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Adapter Run Line", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Adapter Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Adapter Line Report", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Adapter Exception Report", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 6B Preview"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Phase 6A Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Design Gate", frm.doc.design_gate);
            }, __("Evidence"));
        }
    }
});
