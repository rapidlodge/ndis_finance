frappe.ui.form.on("NDIS Governed Next Op Exec Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Governed Next Op Exec Gate Item", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Exec Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Exec Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 11H Preview"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.execution_gate_approved) {
            frm.dashboard.set_headline_alert(
                __("Execution gate approved. One controlled smoke execution can proceed."),
                "green"
            );
        }
    }
});
