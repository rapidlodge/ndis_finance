frappe.ui.form.on("NDIS Controlled Production Batch Policy Review Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Review Items"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Policy Review Gate Item", {
                policy_review_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Policy Review Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Policy Review Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Policy Review Guardrail Report");
        }, __("Open"));

        if (frm.doc.phase8g_freeze) {
            frm.add_custom_button(__("Open Phase 8G Freeze"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Evidence Freeze", frm.doc.phase8g_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 8F Rollback"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_limited_policy_design) {
            frm.dashboard.set_headline_alert(
                __("Policy review approved. Ready for limited policy design. Live posting remains disabled."),
                "green"
            );
        }
    }
});
