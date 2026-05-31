frappe.ui.form.on("NDIS Real Remittance PE Design Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Design Gate Item", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Design Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Design Exception Report", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Source Readiness"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Source Readiness Report");
        }, __("Open"));

        if (frm.doc.phase5k_freeze) {
            frm.add_custom_button(__("Open Phase 5K Freeze"), () => {
                frappe.set_route("Form", "NDIS PE Live Smoke Completion Freeze", frm.doc.phase5k_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.phase5j_rollback_run) {
            frm.add_custom_button(__("Open Phase 5J Rollback"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Rollback Run", frm.doc.phase5j_rollback_run);
            }, __("Evidence"));
        }
    }
});
