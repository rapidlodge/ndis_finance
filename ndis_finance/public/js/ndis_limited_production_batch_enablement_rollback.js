frappe.ui.form.on("NDIS Limited Production Batch Enablement Rollback Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Rollback Line", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.enablement_smoke) {
            frm.add_custom_button(__("Open Phase 9O Smoke"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Smoke Run", frm.doc.enablement_smoke);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.ready_for_enablement_freeze) {
            frm.dashboard.set_headline_alert(
                __("Limited policy enablement rolled back. Ready for evidence freeze."),
                "green"
            );
        }
    }
});
