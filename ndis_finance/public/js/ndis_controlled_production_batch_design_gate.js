frappe.ui.form.on("NDIS Controlled Production Batch Design Gate", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Design Gate Item", { design_gate: frm.doc.name });
        }, __("Open"));
        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Design Gate Report");
        }, __("Open"));
        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Design Exception Report");
        }, __("Open"));
        if (frm.doc.phase7h_freeze) {
            frm.add_custom_button(__("Open Phase 7H Freeze"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch PE Evidence Freeze", frm.doc.phase7h_freeze);
            }, __("Evidence"));
        }
    }
});
