frappe.ui.form.on("NDIS Real Remittance Batch Design Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch Design Gate Item", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Design Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Design Exception Report", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Policy Register"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Policy Register Report");
        }, __("Open"));

        if (frm.doc.evidence_freeze) {
            frm.add_custom_button(__("Open Phase 6H Freeze"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Evidence Freeze", frm.doc.evidence_freeze);
            }, __("Evidence"));
        }
    }
});
